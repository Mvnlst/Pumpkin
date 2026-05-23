use pumpkin_checking::AtomicConstraint;
use pumpkin_checking::CheckerVariable;
use pumpkin_checking::InferenceChecker;

#[derive(Debug, Clone)]
pub struct SCCChecker<Var> {
    pub successors: Box<[Var]>,
}


impl<Var, Atomic> InferenceChecker<Atomic> for SCCChecker<Var>
where
    Var: CheckerVariable<Atomic>,
    Atomic: AtomicConstraint,
{
    // Verify whether the graph is a single SCC. True if not a single SCC; false if it is.
    fn check(
        &self,
        state: pumpkin_checking::VariableState<Atomic>,
        _premises: &[Atomic],
        _consequent: Option<&Atomic>,
    ) -> bool {

        let n = self.successors.len();

        if n <= 1 {return false;}

        let mut visited = vec![false; n];

        // DFS FORWARD
        let mut stack = vec![0];
        while let Some(node_index) = stack.pop() {
            if visited[node_index] {
                continue;
            }
    
            visited[node_index] = true;
    
            let node = &self.successors[node_index];
    
            if let Some(domain) = node.iter_induced_domain(&state) {
                for domain_value in domain {
                    let v = (domain_value - 1) as usize;
    
                    if v < self.successors.len() && !visited[v] {
                        stack.push(v);
                    }
                }
            }
        }
        
        if visited.iter().any(|&x| !x) {
            return true;
        }
        
                
        
        let mut visited_reverse = vec![false; n];

        // DFS BACKWARD
        let mut stack = vec![0];
        while let Some(node_index) = stack.pop() {
            if visited_reverse[node_index] {
                continue;
            }

            visited_reverse[node_index] = true;

            // simulate reverse edges
            for (i, node) in self.successors.iter().enumerate() {
                if let Some(domain) = node.iter_induced_domain(&state) {
                    for v in domain {
                        if (v - 1) as usize == node_index {
                            if !visited_reverse[i] {
                                stack.push(i);
                            }
                        }
                    }
                }
            }
        }

        if visited_reverse.iter().any(|&x| !x) {
            return true;
        }

        false
    }

   
}

#[cfg(test)]
mod tests {
    use pumpkin_checking::TestAtomic;
    use pumpkin_checking::VariableState;

    use super::*;

    fn eq(name: &'static str, value: i32) -> Vec<TestAtomic> {
        vec![TestAtomic {
            name,
            comparison: pumpkin_checking::Comparison::Equal,
            value,
        }]
    }

    fn new_sparse_variable(name: &'static str, mut values: Vec<i32>) -> Vec<TestAtomic> {
        values.sort();
        let mut atoms: Vec<TestAtomic> = Vec::new();

        let atom_gt = TestAtomic {
            name,
            comparison: pumpkin_checking::Comparison::GreaterEqual,
            value: values[0],
        };
        atoms.push(atom_gt);

        let atom_lt = TestAtomic {
            name,
            comparison: pumpkin_checking::Comparison::LessEqual,
            value: values[values.len() - 1],
        };
        atoms.push(atom_lt);

        let mut holes: Vec<i32> = Vec::new();
        let mut prev = values[0] - 1;
        for val in values {
            let mut gap = val - prev;
            while gap > 1 {
                holes.push(prev + gap);
                gap = gap - 1;
            }
            prev = val;
        }

        for hole in holes {
            let atom_hole = TestAtomic {
                name, 
                comparison: pumpkin_checking::Comparison::NotEqual,
                value: hole,
            };
            atoms.push(atom_hole);
        }
        atoms
        
    }

    #[test]
    fn conflict_disconnected_node() {
        // 1 -> 2 -> 1, node 3 outside = NOT a single SCC
        let premises = [
            eq("x1", 2), 
            eq("x2", 1),
        ].concat();

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3"].into(),
        };

        assert!(checker.check(state, &premises, None));
    }

    #[test]
    fn conflict_unreachable_backwards() {
        // no one reaches 1
        let premises = [
            eq("x1", 2), 
            eq("x2", 3),
            eq("x3", 2),
        ].concat();

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3"].into(),
        };

        assert!(checker.check(state, &premises, None));
    }

    #[test]
    fn conflict_conflict_unreachable_backwards2() {
        // 1 reaches all but 2 and 3 reach eachother
        let premises = [
            new_sparse_variable("x1", vec![1, 2, 3]),
            eq("x2", 3), 
            eq("x3", 2),
        ].concat();


        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3"].into(),
        };

        assert!(checker.check(state, &premises, None));
    }

    #[test]
    fn valid_scc() {
        // Valid SCC
        let premises = [
            new_sparse_variable("x1", vec![1, 2, 3]),
            eq("x2", 3), 
            eq("x3", 1),
        ].concat();


        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3"].into(),
        };

        assert!(!checker.check(state, &premises, None));
    }

    #[test]
    fn valid_scc2() {
        // Valid SCC
        let premises = [
            new_sparse_variable("x1", vec![3, 4, 5]),
            new_sparse_variable("x2", vec![1, 3, 5]),
            new_sparse_variable("x3", vec![1, 2, 5]),
            new_sparse_variable("x4", vec![1, 3, 5]),
            new_sparse_variable("x5", vec![1, 2, 3]),

        ].concat();

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3", "x4", "x5"].into(),
        };

        assert!(!checker.check(state, &premises, None));
    }

    #[test]
    fn invalid_scc() {
        // Valid SCC
        let premises = [
            new_sparse_variable("x1", vec![3, 5]),
            new_sparse_variable("x2", vec![1, 3, 5]),
            new_sparse_variable("x3", vec![1, 2, 5]),
            new_sparse_variable("x4", vec![1, 3, 5]),
            new_sparse_variable("x5", vec![1, 2, 3]),

        ].concat();

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = SCCChecker {
            successors: vec!["x1", "x2", "x3", "x4", "x5"].into(),
        };

        assert!(checker.check(state, &premises, None));
    }
}