use pumpkin_checking::AtomicConstraint;
use pumpkin_checking::CheckerVariable;
use pumpkin_checking::InferenceChecker;

#[derive(Debug, Clone)]
pub struct StrongBridgeChecker<Var> {
    pub successors: Box<[Var]>
}


impl<Var, Atomic> InferenceChecker<Atomic> for StrongBridgeChecker<Var>
where
    Var: CheckerVariable<Atomic>,
    Atomic: AtomicConstraint,
{
    // Check: consequent says edge u -> v is necessary to be able to reach v from u
    fn check(
        &self,
        state: pumpkin_checking::VariableState<Atomic>,
        _premises: &[Atomic],
        consequent: Option<&Atomic>,
    ) -> bool {
        
        let Some(consequent) = consequent else {
            return false; // if no consequent this checker is not applicable
        };
        
        if consequent.comparison() != pumpkin_checking::Comparison::Equal {
            return false; // not a propagation we expect
        }

        
        let v = (consequent.value() - 1) as usize;
 
        let u = self.successors.iter().position(|var| var.does_atomic_constrain_self(consequent)).expect("Variable not found in successors");

        
        // DFS FORWARD from u
        let mut visited = vec![false; self.successors.len()];
    
        let mut stack = vec![u];
        while let Some(node_index) = stack.pop() {
            if visited[node_index] {
                continue;
            }
    
            visited[node_index] = true;
    
            let node = &self.successors[node_index];
    
            if let Some(domain) = node.iter_induced_domain(&state) {
                for domain_value in domain {
                    let val = (domain_value - 1) as usize;
    
                    if val < self.successors.len() && !visited[val] {
                        eprintln!("{} -> {}", node_index + 1, val + 1);
                        stack.push(val);
                    } else {
                        eprintln!("{} -> {}", node_index + 1, val + 1);
                    }
                }
            }
        }
        
        // If we can still reach v without the edge from u to v, explanation is invalid
        if visited[v] {
            return false;
        }

        true
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
                gap = gap - 1;
                holes.push(prev + gap);
                
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
    fn no_consequent_test() {
        // 1 -> 2 -> 1, node 3 outside = NOT a single SCC
        let premises = [
            eq("x1", 2), 
            eq("x2", 1),
        ].concat();

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), None)
            .expect("no conflicting atomics");

        let checker = StrongBridgeChecker {
            successors: vec!["x1", "x2", "x3"].into(),
        };

        assert!(!checker.check(state, &premises, None));
    }

    #[test]
    fn strong_bridge_propagation() {
        // 1 -> 2 -> 1, node 3 outside = NOT a single SCC
        let premises = [
            new_sparse_variable("x1", vec![3, 4, 5]),
            new_sparse_variable("x2", vec![1, 3, 5]),
            new_sparse_variable("x3", vec![1, 2, 5]),
            new_sparse_variable("x4", vec![1, 3, 5]),
            new_sparse_variable("x5", vec![1, 2, 3]),
        ].concat();

        let consequent = eq("x1", 4)[0];

        let state = VariableState::prepare_for_conflict_check(premises.iter().cloned(), Some(consequent))
            .expect("no conflicting atomics");

        let checker = StrongBridgeChecker {
            successors: vec!["x1", "x2", "x3", "x4", "x5"].into(),
        };

        assert!(checker.check(state, &premises, Some(&consequent)));
    }
}