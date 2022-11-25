import torch
import numpy as np

from .dagsched_env import DagSchedEnv
from ..utils import metrics



def env_run(rank, datagen, conn):
    torch.manual_seed(rank)
    np.random.seed(rank)

    env = DagSchedEnv(rank)
    shared_obs_tensor = None
    first_episode = True

    while header_data := conn.recv():
        header, data = header_data

        if header == 'reset':
            if not first_episode:
                avg_job_duration = metrics.avg_job_duration(env)
                n_completed_jobs = env.n_completed_jobs
            else:
                avg_job_duration, n_completed_jobs = None, None

            n_job_arrivals, n_init_jobs, mjit, n_workers, x_ptrs, shared_obs_tensor = data
            _env_reset(env, datagen, n_job_arrivals, n_init_jobs, mjit, n_workers, x_ptrs)

            first_episode = False
            conn.send((avg_job_duration, n_completed_jobs))
            
        elif header == 'step':
            if shared_obs_tensor is None:
                raise Exception(f'proc {rank} is trying to step before resetting')
            (job_id, op_id), prlvl = data
            _env_step(rank, env, job_id, op_id, prlvl, shared_obs_tensor)
            conn.send(None)

        else:
            raise Exception(f'proc {rank} received invalid data')



def _env_reset(env, datagen, n_job_arrivals, n_init_jobs, mjit, n_workers, x_ptrs):
    initial_timeline = datagen.initial_timeline(
        n_job_arrivals, n_init_jobs, mjit)
    workers = datagen.workers(n_workers)

    env.reset(initial_timeline, workers, x_ptrs)



def _env_step(rank, env, job_id, op_id, prlvl, shared_obs_tensor):
    reward, done = env.step(job_id, op_id, prlvl)

    active_jobs_msk = torch.zeros(env.n_job_arrivals, dtype=torch.bool)
    active_jobs_msk[env.active_job_ids] = 1

    put_data = [
        torch.tensor([env.are_actions_available]),
        env.construct_op_msk().flatten(),
        env.construct_prlvl_msk().flatten(), 
        active_jobs_msk,
        torch.tensor([len(env.avail_worker_ids)]),
        torch.tensor([reward]), 
        torch.tensor([done])
    ]

    torch.cat(put_data, out=shared_obs_tensor)



