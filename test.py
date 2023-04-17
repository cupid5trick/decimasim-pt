import os
import shutil
import sys


import pandas as pd
import numpy as np
import torch
from torch.multiprocessing import set_start_method, Pool
import gymnasium as gym
import matplotlib.pyplot as plt

from spark_sched_sim.wrappers.decima_wrappers import (
    DecimaObsWrapper,
    DecimaActWrapper
)
from spark_sched_sim.metrics import avg_job_duration
from train_algs.utils.hidden_prints import HiddenPrints
from spark_sched_sim.schedulers import DecimaScheduler, FIFOScheduler, CPTScheduler


def main():
    setup()

    print('testing', flush=True)

    num_tests = 10

    num_executors = 50

    # should be greater than the number of epochs the
    # model was trained on, so that the job sequences
    # are unseen
    base_seed = 500 # NOTE: model does awful on 503

    model_dir = 'ignore/models'
    model_name = 'model.pt'

    fifo_scheduler = FIFOScheduler(num_executors)
    scpt_scheduler = CPTScheduler(num_executors)
    lcpt_scheduler = CPTScheduler(num_executors, by_shortest=False)
    decima_scheduler = \
        DecimaScheduler(
            num_executors,
            training_mode=False, 
            state_dict_path=f'{model_dir}/{model_name}'
        )

    env_kwargs = {
        'num_executors': num_executors,
        'num_init_jobs': 1,
        'num_job_arrivals': 100,
        'job_arrival_rate': 1/25000,
        'moving_delay': 2000.
    }

    env_id = 'spark_sched_sim:SparkSchedSimEnv-v0'
    base_env = gym.make(env_id, **env_kwargs)
    wrapped_env = DecimaActWrapper(DecimaObsWrapper(base_env))

    test_instances = [
        (fifo_scheduler, base_env, num_tests, base_seed),
        (scpt_scheduler, base_env, num_tests, base_seed),
        (lcpt_scheduler, base_env, num_tests, base_seed),
        (decima_scheduler, wrapped_env, num_tests, base_seed)
    ]

    # run tests in parallel using multiprocessing
    with Pool(len(test_instances)) as p:
        test_results = p.map(test, test_instances)

    sched_names = [sched.name for sched, *_ in test_instances]

    visualize_results(
        'job_duration_cdf.png', 
        sched_names, 
        test_results,
        env_kwargs
    )



def test(instance):
    sys.stdout = open(f'ignore/log/proc1/main.out', 'a')
    torch.set_num_threads(1)

    sched, env, num_tests, base_seed = instance

    avg_job_durations = []

    for i in range(num_tests):
        torch.manual_seed(42)

        with HiddenPrints():
            run_episode(env, sched, base_seed + i)

        result = avg_job_duration(env)*1e-3
        avg_job_durations += [result]
        print(f'{sched.name}: test {i+1}, avj={result:.1f}s', flush=True)

    return np.array(avg_job_durations)




def compute_CDF(arr, num_bins=100):
    """
    usage: x, y = compute_CDF(arr):
           plt.plot(x, y)
    """
    values, base = np.histogram(arr, bins=num_bins)
    cumulative = np.cumsum(values)
    return base[:-1], cumulative / float(cumulative[-1])




def run_episode(env, sched, seed): 
    env_options = {'max_wall_time': np.inf} 
    obs, _ = env.reset(seed=seed, options=env_options)

    done = False
    rewards = []
    
    while not done:
        if isinstance(sched, DecimaScheduler):
            action, *_ = sched(obs)
        else:
            action = sched(obs)

        obs, reward, terminated, truncated, _ = env.step(action)

        rewards += [reward]
        done = (terminated or truncated)

    return rewards



def visualize_results(
    out_fname, 
    sched_names, 
    test_results,
    env_kwargs
):
    # plot CDF's
    for sched_name, avg_job_durations in zip(sched_names, test_results):
        x, y = compute_CDF(avg_job_durations)
        plt.plot(x, y, label=sched_name)

    # display environment options in a table
    plt.table(
        cellText=[[key,val] for key,val in env_kwargs.items()],
        colWidths=[.25, .1],
        cellLoc='center', 
        rowLoc='center',
        loc='right'
    )

    plt.tight_layout()
    plt.legend(bbox_to_anchor=(1, 1), loc='upper left')
    plt.xlabel('Average job duration (s)')
    plt.ylabel('CDF')
    num_tests = len(test_results[0])
    plt.title(f'CDF of avg. job duration over {num_tests} runs')
    plt.savefig(out_fname, bbox_inches='tight')




def setup():
    shutil.rmtree('ignore/log/proc1/', ignore_errors=True)
    os.mkdir('ignore/log/proc1/')

    sys.stdout = open(f'ignore/log/proc1/main.out', 'a')

    set_start_method('forkserver')

    torch.manual_seed(42)




if __name__ == '__main__':
    main()