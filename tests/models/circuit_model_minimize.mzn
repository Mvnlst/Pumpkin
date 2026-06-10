include "globals.mzn";

int: n;
array[1..n] of var 1..n: x;
array[1..n] of set of int: allowed;
array[1..n, 1..n] of int: dist;

% Nodes can only be assigned a successor if there is an edge
constraint forall(i in 1..n)(
    x[i] in allowed[i]
);

constraint pumpkin_circuit(x);

var int: total_cost;
constraint total_cost = sum(i in 1..n)(dist[i, x[i]]);

solve :: int_search(x, input_order, indomain_min, complete)
       minimize total_cost;

