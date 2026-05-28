use fixedbitset::FixedBitSet;
use pumpkin_core::conjunction;
use pumpkin_core::create_statistics_struct;
use pumpkin_core::declare_inference_label;
use pumpkin_core::predicate;
use pumpkin_core::predicates::PropositionalConjunction;
use pumpkin_core::proof::ConstraintTag;
use pumpkin_core::proof::InferenceCode;
use pumpkin_core::propagation::DomainEvents;
use pumpkin_core::propagation::Domains;
use pumpkin_core::propagation::LocalId;
use pumpkin_core::propagation::PropagationContext;
use pumpkin_core::propagation::Propagator;
use pumpkin_core::propagation::PropagatorConstructor;
use pumpkin_core::propagation::ReadDomains;
use pumpkin_core::state::Conflict;
use pumpkin_core::state::PropagationStatusCP;
use pumpkin_core::state::PropagatorConflict;
use pumpkin_core::statistics::Statistic;
use pumpkin_core::variables::IntegerVariable;
use pumpkin_core::propagation::InferenceCheckers;

use crate::circuit::CircuitChecker;
use crate::circuit::SCCChecker;
use crate::circuit::StrongBridgeChecker;
use crate::circuit::options::CircuitPropagationMethod;


// constructor for the propagator. ConstraintTag is for proof logging
#[derive(Debug, Clone)]
pub struct CircuitConstructor<Var> {
    pub successors: Box<[Var]>,
    pub constraint_tag: ConstraintTag,
    pub propagation_method: CircuitPropagationMethod,
}

// Propagator struct. Contains propagator info and inference code (latter for explanations)
#[derive(Debug, Clone)]
pub struct CircuitPropagator<Var> {
    pub successors: Box<[Var]>,
    inference_code: InferenceCode,
    strong_bridge_code: InferenceCode,
    scc_code: InferenceCode,
    statistics: StrongBridgeStatistics,
    use_strong_bridges: bool, // bool indicating whether to use the extension. Can be changed to use the enum itself if more extension are added.
}

impl<Var> PropagatorConstructor 
    for CircuitConstructor<Var> 
where 
    Var : IntegerVariable + 'static, 
{
    type PropagatorImpl = CircuitPropagator<Var>;

    fn create(
        self,
        mut context: pumpkin_core::propagation::PropagatorConstructorContext,
    ) -> Self::PropagatorImpl {
        // registering for domain events; when should our propagator be enqueued. 
        // so go through all successors and add 'listeners' to all of them.

        
        let event = match self.propagation_method {
            // base cycle prevention only needs to register for ASSIGN (as it looks only at enforced edges)
            CircuitPropagationMethod::Base => DomainEvents::ASSIGN,
            // Strong bridge extension needs to register for any domain change as those can trigger new strong bridges
            CircuitPropagationMethod::StrongBridges => DomainEvents::ANY_INT,
        };

        
        self.successors
            .iter()
            .enumerate()
            .for_each(|(index, successor)| {
                context.register(
                    successor.clone(),
                    event,
                    LocalId::from(index as u32),
                );
                context.register_backtrack(
                    successor.clone(),
                    event,
                    LocalId::from(index as u32),
                );
            });

        // create the actual propagator and generate new inference code
        CircuitPropagator {
            // set variables to base values
            successors: self.successors,
            inference_code: InferenceCode::new(self.constraint_tag, CircuitPrevent),
            strong_bridge_code: InferenceCode::new(self.constraint_tag, StrongBridge),
            scc_code: InferenceCode::new(self.constraint_tag, SCCCheck),
            statistics: StrongBridgeStatistics::default(),
            use_strong_bridges: self.propagation_method == CircuitPropagationMethod::StrongBridges,
        }
    }

    // inference checker
    fn add_inference_checkers(&self, mut checkers: InferenceCheckers<'_>) {
        checkers.add_inference_checker(
            InferenceCode::new(self.constraint_tag, CircuitPrevent),
            Box::new(CircuitChecker {
                successors: self.successors.clone(),
            }),
        );
        checkers.add_inference_checker(
            InferenceCode::new(self.constraint_tag, StrongBridge),
            Box::new(StrongBridgeChecker {
                successors: self.successors.clone(),
            }),
        );
        checkers.add_inference_checker(
            InferenceCode::new(self.constraint_tag, SCCCheck),
            Box::new(SCCChecker {
                successors: self.successors.clone(),
            }),
        );
    }
}

declare_inference_label!(CircuitPrevent);
declare_inference_label!(StrongBridge);
declare_inference_label!(SCCCheck);

 create_statistics_struct!(StrongBridgeStatistics {
            number_of_sb_propagations: usize,
            number_of_scc_propagations: usize,
        });


// here comes an implementation of Propagator which has some basic functions (like defining the name) but also important functions propagate() and propagate_from_scratch()
impl<Var: IntegerVariable + 'static> Propagator for CircuitPropagator<Var> {
    fn name(&self) -> &str {
    "Circuit"
    }

    fn propagate_from_scratch(&self, mut context: PropagationContext) -> PropagationStatusCP {
        // Should happen only on first call; check for single SCC here as well
        self.remove_self_loops(&mut context)?;
        self.check(context.domains())?;
        self.prevent(&mut context)?;

        if self.use_strong_bridges {
             self.strong_bridge_prevent(&mut context)?;
        }
        Ok(())
    }

    fn log_statistics(&self, statistic_logger: pumpkin_core::statistics::StatisticLogger) {
        self.statistics.log(statistic_logger);
    }

    fn propagate(&mut self, mut context: PropagationContext) -> PropagationStatusCP {
        self.remove_self_loops(&mut context)?;
        self.check(context.domains())?;
        self.prevent(&mut context)?;

        if self.use_strong_bridges {
            self.strong_bridge_prevent_with_stats(&mut context)?;
        }
        Ok(())
    }
}

impl<Var: IntegerVariable + 'static> CircuitPropagator<Var> {
    fn remove_self_loops(&self, context: &mut PropagationContext) -> PropagationStatusCP {
        for (zero_indexed_node, domain_of_one_indexed_node) in self.successors.iter().enumerate() {
            context.post(
                predicate!(domain_of_one_indexed_node != index_to_domain_value(zero_indexed_node)),
                conjunction!(),
                &self.inference_code,
            )?;
        }
        Ok(())
    }
}

impl<Var: IntegerVariable + 'static> CircuitPropagator<Var> {    
    fn strong_bridge_prevent(&self, context: &mut PropagationContext) -> PropagationStatusCP {
        // Validate graph is a single SCC
        if !self.is_strongly_connected(context) {
            return Err(Conflict::Propagator(PropagatorConflict {
                        conjunction: self.create_full_graph_explanation(context.domains()),
                        inference_code: self.scc_code.clone(),
                }));
        }
        // self.print_current_domains(context);
        
        // Detect strong bridges, which will be edges that have to be enforced. Also keep track of how far you can reach from that node.
        let mut required_edges: Vec<(usize, usize, Vec<bool>)> = Vec::new();


        // Loop over every node
        for (u, node) in self.successors.iter().enumerate() {
            let domain: Vec<i32> = context.iterate_domain(node).collect();

            // If only one edge, it is already fixed
            if domain.len() <= 1 {
                continue;
            }

            // Check for every edge if it is a strong bridge; can u reach v without taking direct edge?
            for v in domain {
                let v = domain_value_to_index(v);
                let (reachable, visited) = self.reachable_without_edge(context, u, v);
                if !reachable {
                    required_edges.push((u, v, visited));
                }
            }

        }
        
        // Enforce the required_edges. Every u needs to go to v.
        for (u, v, visited) in required_edges {
            let reason = self.create_strong_bridge_explanation(context.domains(), &visited, u, v);
            context.post(
                predicate!(self.successors[u] == index_to_domain_value(v)),
                reason,
                &self.strong_bridge_code,
            )?;
        }
        Ok(())
    }

    fn strong_bridge_prevent_with_stats(&mut self, context: &mut PropagationContext) -> PropagationStatusCP {
        // Validate graph is a single SCC
        if !self.is_strongly_connected(context) {
            self.statistics.number_of_scc_propagations += 1;
            return Err(Conflict::Propagator(PropagatorConflict {
                        conjunction: self.create_full_graph_explanation(context.domains()),
                        inference_code: self.scc_code.clone(),
                }));
        }
        
        // Detect strong bridges, which will be edges that have to be enforced. Also keep track of how far you can reach from that node.
        let mut required_edges: Vec<(usize, usize, Vec<bool>)> = Vec::new();


        // Loop over every node
        for (u, node) in self.successors.iter().enumerate() {
            let domain: Vec<i32> = context.iterate_domain(node).collect();

            // If only one edge, it is already fixed
            if domain.len() <= 1 {
                continue;
            }

            // Check for every edge if it is a strong bridge; can u reach v without taking direct edge?
            for v in domain {
                let v = domain_value_to_index(v);
                let (reachable, visited) = self.reachable_without_edge(context, u, v);
                if !reachable {
                    required_edges.push((u, v, visited));
                }
            }

        }
        
        // Enforce the required_edges. Every u needs to go to v.
        for (u, v, visited) in required_edges {
            self.statistics.number_of_sb_propagations += 1;
            let reason = self.create_strong_bridge_explanation(context.domains(), &visited, u, v);
            // let reason = self.create_full_graph_explanation(context.domains());
            context.post(
                predicate!(self.successors[u] == index_to_domain_value(v)),
                reason,
                &self.strong_bridge_code,
            )?;
        }
        Ok(())
    }


    fn create_strong_bridge_explanation(&self, context: Domains, visited: &[bool], u: usize, v: usize) -> PropositionalConjunction {
        // Different option: Provide Generic explanations by giving the WHOLE context as reason
        
        let mut explanation = Vec::new();
        

        for (node_index, &reachable) in visited.iter().enumerate() {
            if !reachable {
                continue;
            }

            let node = &self.successors[node_index];

            let domain_id = node.lower_bound_predicate(0).get_domain();

            let initial_domain: Vec<i32>  = context.iterate_initial_domain(domain_id).collect();
            
            let current_domain: Vec<i32> = context.iterate_domain(node).collect();

            for domain_value in initial_domain {
                if !current_domain.contains(&domain_value) {
                    // i is the 0-based index of the node to which there was an edge in the initial problem, but currently that edge is pruned.
                    let i = domain_value_to_index(domain_value);

                    // i should never be visited by default. We also make sure we do not accidentally include the strong bridge in the reason
                    if !visited[i] && !(node_index == u && i == v) {
                        // We find an edge that crosses reachable -> unreachable, it is currently pruned however.
                        // This implicitly means this edge is not included in the current state, as otherwise "i" would have been reachable
                        explanation.push(predicate!(
                            node != domain_value
                        ));
                    }
                }
            }
        }
        return explanation.into_iter().collect();
    }
    
    fn reachable_without_edge(&self, context: &PropagationContext, start: usize, target: usize) -> (bool, Vec<bool>) {

        let n = self.successors.len();
        let mut visited = vec![false; n];
        let mut stack = vec![start];

        while let Some(current_node_index) = stack.pop() {

            if visited[current_node_index] {
                continue;
            }

            visited[current_node_index] = true;
            
            
            if current_node_index == target {
                return (true, visited);
            }

            let current_node = &self.successors[current_node_index];

            for next in context.iterate_domain(current_node) {
                let next_node_index = domain_value_to_index(next);

                // Skip edge if it is the direct connection between start and target
                if current_node_index == start && next_node_index == target {
                    continue;
                }

                if !visited[next_node_index] {
                    stack.push(next_node_index);
                }
            }
        }

        (false, visited)
    }

    
    // Makes sure the graph is strongly connected
    fn is_strongly_connected(&self, context: &PropagationContext) -> bool {
        let n = self.successors.len();

        if n <= 1 {return true;}

        let mut visited = vec![false; n];
        self.dfs_forward(context, 0, &mut visited);

        if visited.iter().any(|&x| !x) {
            return false;
        }

        let mut visited_reverse = vec![false; n];
        self.dfs_backward(context, 0, &mut visited_reverse);

        if visited_reverse.iter().any(|&x| !x) {
            return false;
        }

        true
    }

    // Check if we can reach all nodes from a starting node
    fn dfs_forward(&self, context: &PropagationContext, start: usize, visited: &mut Vec<bool>) {
        let mut stack = vec![start];

        while let Some(node_index) = stack.pop() {
            if visited[node_index] {
                continue;
            }
            visited[node_index] = true;

            let node: &Var = &self.successors[node_index];

            for domain_value in context.iterate_domain(node) {
                let v = domain_value_to_index(domain_value);
                if v < self.successors.len() && !visited[v] {
                    stack.push(v);
                }
            }
        }
    }

    // Check if we can reach the starting node from all nodes
    fn dfs_backward(&self, context: &PropagationContext, start: usize, visited_reverse: &mut Vec<bool>) {
        let mut stack = vec![start];

        while let Some(node_index) = stack.pop() {
            if visited_reverse[node_index] {
                continue;
            }
            visited_reverse[node_index] = true;

            for (i, node) in self.successors.iter().enumerate() {
                for v in context.iterate_domain(node) {
                    if domain_value_to_index(v) == node_index {
                        stack.push(i);
                    }
                }
            }
        }
    }

    fn create_full_graph_explanation(&self, context: Domains) -> PropositionalConjunction {
        
        let mut explanation = Vec::new();

        for node in &self.successors {

            let lb = context.lower_bound(node);
            
            explanation.push(predicate!(
                node >= lb
            ));

            let ub = context.upper_bound(node);
            explanation.push(predicate!(
                node <= ub
            ));
            
            for hole in context.get_holes(node) {
                explanation.push(predicate!(
                    node != hole
                ));
            }

        }

        explanation.into_iter().collect()
    }
}   

impl<Var: IntegerVariable + 'static> CircuitPropagator<Var> {
    fn prevent(&self, context: &mut PropagationContext) -> PropagationStatusCP {
        // collect all nodes that have an incoming enforced/fixed edge, these cannot be start of possible chains
        let mut has_incoming_edge = FixedBitSet::with_capacity(self.successors.len());
        // for every fixed edge we find, we follow it and add the resulting node to the list
        for successor in self.successors.iter() {
            if let Some(fixed_value) = context.fixed_value(successor) {
                has_incoming_edge.insert(domain_value_to_index(fixed_value));
            }
        }



        // For every node that has no fixed incoming edge, we try to create a chain.
        for unmarked in has_incoming_edge.zeroes() {
            // If the node has no fixed outgoing edge, we cannot create a chain and go to the next possible node to start a chain.
            let Some(fixed_value) = context.fixed_value(&self.successors[unmarked]) else {
                continue;
            };

            // If it does have an outgoing fixed edge, we can start creating a chain with our starting node.
            let mut chain = vec![unmarked];

            // Now we keep up extending our chain as long as we reach nodes that have a fixed outgoing edge.
            // We already know the upcoming node as we checked if the first node had a fixed outgoing edge;
            let mut next = domain_value_to_index(fixed_value);
            // And then we keep on looping until we end up in a node with no fixed outgoing edge.
            while let Some(fixed_value_next) = context.fixed_value(&self.successors[next]) {
                // We add the next value to the chain
                chain.push(next);
                // And continue to unfold the chain from there. As the domains themselves are 1-indexed, we need to transform them to 0-indexed for our own array.
                next = domain_value_to_index(fixed_value_next);

                // If the chain already contained this node, we found a subcycle due to our previous prunings in this method call
                if chain.contains(&next) {
                    break;
                }
            }

            // We have found a chain. If the last node in the chain has a possible edge to the starting node, we prune that edge only if
            // the length of the chain is not n: if we have not visited all nodes yet we cannot return to the starting node already.
            if context.contains(&self.successors[next], index_to_domain_value(unmarked)) && chain.len() + 1< self.successors.len() {
                let reason = self.create_prevent_explanation(context.domains(), &chain);
                context.post(
                    predicate!(self.successors[next] != index_to_domain_value(unmarked)),
                    reason,
                    &self.inference_code,
                )?;
            }
        }

        Ok(())
    }

    fn create_prevent_explanation(
        &self,
        context: Domains,
        path: &[usize],
    ) -> PropositionalConjunction {
        path.iter()
            .map(|&index| {
                let var = &self.successors[index];

                predicate!(
                    var == context
                        .fixed_value(var)
                        .expect("Expected every variable in the chain to be assigned")
                )
            })
            .collect()
    }

    
}    

impl<Var: IntegerVariable + 'static> CircuitPropagator<Var> {
    fn check(&self, context: Domains) -> PropagationStatusCP {
        let n = self.successors.len();

        for start in 0..n {
            let mut visited = FixedBitSet::with_capacity(n);
            let mut cycle_path = Vec::new();

            let mut current = start;

            loop {
                // get the domain of the current node
                let domain = &self.successors[current];

                // check if the node already has an enforced edge
                let Some(fixed_value) = context.fixed_value(domain) else {
                    // if no edge is enforced, we stop following the cycle
                    break;
                };

                // if we already visited this node before
                if visited.contains(current) {
                    // check if we visited all nodes in this iteration and whether we would go to the starting node,
                    // creating a Hamiltonian cycle
                    if visited.count_ones(..) == n &&  current == start {
                        return Ok(());
                    }

                    // Otherwise, we raise a conflict
                    return Err(Conflict::Propagator(PropagatorConflict {
                        conjunction: self.create_check_explanation(context, &cycle_path),
                        inference_code: self.inference_code.clone(),
                    }));
                }

                visited.insert(current);
                cycle_path.push(current);

                let next_index = domain_value_to_index(fixed_value);
                if next_index >= n {
                    break;
                    // should not happen; nodes should not be able to refer outside of range
                }
                current = next_index;
            }

        }
        Ok(())
    }

    fn create_check_explanation(
        &self,
        context: Domains,
        cycle: &[usize],
    ) -> PropositionalConjunction {
        cycle
            .iter()
            .map(|&index| {
                let var = &self.successors[index];

                predicate!(
                    var == context
                        .fixed_value(var)
                        .expect("Found a subcycle")
                )
            })
            .collect()
    }
}


const VALUE_OFFSET: usize = 1;

#[inline]
fn domain_value_to_index(domain_value: i32) -> usize {
    domain_value as usize - VALUE_OFFSET
}

#[inline]
fn index_to_domain_value(index: usize) -> i32 {
    index as i32 + VALUE_OFFSET as i32
}

#[cfg(test)]
mod tests { 
    use pumpkin_core::{propagation::ReadDomains, state::State};

    use crate::circuit::{CircuitConstructor, options::CircuitPropagationMethod};

    //VALID FULL HAMILTONIAN PATH (NO CONFLICT)
    #[test]
    fn circuit_hamiltonian_path_conflict_detection() {
        let mut state = State::default();

        let x = state.new_interval_variable(2, 2, None);
        let y = state.new_interval_variable(3, 3, None);
        let z = state.new_interval_variable(1, 1, None);

        let constraint_tag = state.new_constraint_tag();

        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y, z].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();

        assert!(
            result.is_ok(),
            "If there is a cycle concerning all variables, then no conflict should be reported"
        )
    }
    // SIMPLE SUBCYCLE (SHOULD CONFLICT)
    #[test]
    fn circuit_conflict_detection_simple() {
        let mut state = State::default();

        let x = state.new_interval_variable(2, 2, None);
        let y = state.new_interval_variable(1, 1, None);
        let z = state.new_interval_variable(1, 3, None);

        let constraint_tag = state.new_constraint_tag();

        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y, z].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();

        assert!(
            result.is_err(),
            "If there is a cycle concerning all variables, then no conflict should be reported"
        )
    }

    // SELF LOOP REMOVAL 
    #[test]
    fn circuit_removes_self_loops() {
        let mut state = State::default();
        let x = state.new_interval_variable(1, 3, None);
        let y = state.new_interval_variable(1, 3, None);
        let z = state.new_interval_variable(1, 3, None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y, z].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let _ = state.propagate_to_fixed_point();
        assert!(
            !state.get_domains().contains(&x, 1), 
            "Self-loop x=1 mst be removed"
        );
    }

    //SELF LOOP FIXED (CONFLICT)
    #[test]
    fn circuit_self_loop_fixed() {
        let mut state = State::default();
        let x = state.new_interval_variable(1, 1, None);
        let y = state.new_interval_variable(1, 3, None);
        let z = state.new_interval_variable(1, 3, None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y, z].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_err(), "Forced self-loop = conflict");

    }

    //Prevent should not prune closing hamilton cycle edge
    #[test]
    fn circuit_prevent_not_prune_closing_edge() {
        let mut state = State::default();
        let x = state.new_interval_variable(2, 2, None); 
        let y = state.new_interval_variable(3, 3, None); 
        let z = state.new_interval_variable(1, 3, None); 

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y, z].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let _ = state.propagate_to_fixed_point();

        assert!(
        state.get_domains().contains(&z, 1),
        "Closing edge z-x completes a full Hamiltonian cycle and must NOT be pruned"
    );
    }

    //Edge case: single variable must conflict
    #[test]
    fn circuit_single_variable_conflict() {
        let mut state = State::default();

        let x = state.new_interval_variable(1, 1, None);

       let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_err(), "Single node with self-loop must conflict");
    }

    //test two variables okey
    #[test]
    fn circuit_two_variable_cycle_ok() {
        let mut state = State::default();

        let x = state.new_interval_variable(2, 2, None);
        let y = state.new_interval_variable(1, 1, None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x, y].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_ok(), "2-cycle is a valid Hamiltonian cycle");
    }

    //test strong bridge detection
    #[test]
    fn circuit_strong_bridge() {
        let mut state = State::default();

        let x1 = state.new_sparse_variable(vec![4, 6], None);
        let x2 = state.new_sparse_variable(vec![3, 4], None);
        let x3 = state.new_sparse_variable(vec![1, 2], None);
        let x4 = state.new_sparse_variable(vec![1, 6], None);
        let x5 = state.new_sparse_variable(vec![2, 6], None);
        let x6 = state.new_sparse_variable(vec![1, 4, 5], None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x1, x2, x3, x4, x5, x6].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_ok(), "2-cycle is a valid Hamiltonian cycle");
        assert!(state.get_domains().contains(&x6, 5), "Strong bridge must be enforced!")
    }

    #[test]
    fn circuit_strong_bridge2() {
        let mut state = State::default();

        let x1 = state.new_sparse_variable(vec![2, 5], None);
        let x2 = state.new_sparse_variable(vec![1, 3, 4], None);
        let x3 = state.new_sparse_variable(vec![2, 5], None);
        let x4 = state.new_sparse_variable(vec![3], None);
        let x5 = state.new_sparse_variable(vec![1, 2], None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x1, x2, x3, x4, x5].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_ok(), "2-cycle is a valid Hamiltonian cycle");
        // assert!(!state.get_domains().contains(&x5, 2), "Strong bridge must be enforced!")
    }

    #[test]
    fn circuit_articulation_point_conflict() {
        let mut state = State::default();

        let x1 = state.new_interval_variable(2, 2, None);
        let x2 = state.new_interval_variable(1, 4, None);
        let x3 = state.new_interval_variable(2, 2, None);
        let x4 = state.new_interval_variable(2, 2, None);

        let constraint_tag = state.new_constraint_tag();

        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x1, x2, x3, x4].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();

        assert!(
            result.is_err(),
            "A possible graph with an articulation point cannot contain a Hamiltonian circuit"
        );
    }

    #[test]
    fn circuit_strong_bridge3() {
        let mut state = State::default();

        let x1 = state.new_sparse_variable(vec![4, 5], None);
        let x2 = state.new_sparse_variable(vec![1, 3], None);
        let x3 = state.new_sparse_variable(vec![4], None);
        let x4 = state.new_sparse_variable(vec![2, 3], None);
        let x5 = state.new_sparse_variable(vec![3], None);

        let constraint_tag = state.new_constraint_tag();
        let _ = state.add_propagator(CircuitConstructor {
            successors: vec![x1, x2, x3, x4, x5].into(),
            constraint_tag,
            propagation_method: CircuitPropagationMethod::StrongBridges,
        });

        let result = state.propagate_to_fixed_point();
        assert!(result.is_ok(), "2-cycle is a valid Hamiltonian cycle");
        // assert!(!state.get_domains().contains(&x5, 2), "Strong bridge must be enforced!")
    }

}