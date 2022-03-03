import typing
from dataclasses import dataclass

import numpy as np
import networkx as nx

from args import args
from dagsched_utils import triangle, invalid_time
from .stage import Stage


@dataclass
class Job:
    INVALID_ID = args.n_jobs


    id_: int = INVALID_ID

    # lower triangle of the dag's adgacency 
    # matrix stored as a flattened array
    dag: np.ndarray = np.zeros(triangle(args.max_stages))

    # arrival time of this job
    t_arrival: np.ndarray = invalid_time()

    t_completed: np.ndarray = invalid_time()

    # tuple of stages that make up the
    # nodes of the dag
    stages: typing.Tuple[Stage, ...] = \
        tuple([Stage() for _ in range(args.max_stages)])

    # number of stages this job consists of
    n_stages: int = 0

    n_completed_stages: int = 0


    @property
    def max_stages(self):
        return len(self.stages)

    @property
    def is_complete(self):
        return self.n_completed_stages == self.n_stages


    def add_stage_completion(self):
        assert self.n_completed_stages < self.n_stages
        self.n_completed_stages += 1


    def dag_to_nx(self):
        # construct adjacency matrix from flattend
        # lower triangle array
        n = self.max_stages
        T = np.zeros((n,n))
        T[np.tril_indices(n,-1)] = self.dag

        # truncate adjacency matrix to only include valid nodes
        n = self.n_stages
        T = T[:n,:n]

        G = nx.convert_matrix.from_numpy_matrix(T, create_using=nx.DiGraph)
        assert nx.is_directed_acyclic_graph(G)
        return G


    def find_src_nodes(self):
        '''`dag` is a flattened lower triangle'''
        G = self.dag_to_nx()
        sources = [node for node,in_deg in G.in_degree() if in_deg==0]
        return sources


    def find_new_frontiers(self, stage):
        '''if `stage` is completed, returns all of its
        successors whose other dependencies are also 
        completed, if any exists.
        '''
        if not stage.is_complete:
            return []

        G = self.dag_to_nx()
        new_frontiers = []
        # search through successors of `stage`
        for suc_stage_id in G.successors(stage.id_):
            # if all dependencies are completed, then
            # add this successor to the frontiers
            if self._check_dependencies(G, suc_stage_id):
                new_frontiers += [suc_stage_id]
        
        return new_frontiers


    def _check_dependencies(self, G, stage_id):
        '''checks if all the dependencies of `stage_id`
        are completed.
        '''
        for dep_id in G.predecessors(stage_id):
            dep_stage = self.stages[dep_id]
            if not dep_stage.is_complete:
                return False

        return True