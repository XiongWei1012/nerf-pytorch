"""
Script to run and cache a dataset (ray bundles and ground-truth values)
for faster train-eval loops.
"""

import argparse
import os
import time
import yaml

import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm, trange

import models
from cfgnode import CfgNode
from load_blender import load_blender_data
from metrics import ScalarMetric
from nerf_helpers import get_minibatches, get_ray_bundle
from nerf_helpers import img2mse, meshgrid_xy, mse2psnr
from train_utils import predict_and_render_radiance
from train_utils import eval_nerf
from train_utils import run_network, run_one_iter_of_nerf


def cache_nerf_dataset(args):
    images, poses, render_poses, hwf, i_split = load_blender_data(
        args.datapath, half_res=args.halfres, testskip=args.stride
    )

    i_train, i_val, i_test = i_split
    H, W, focal = hwf
    H, W = int(H), int(W)
    hwf = [H, W, focal]

    # Device on which to run.
    if torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    os.makedirs(os.path.join(args.savedir, "train"), exist_ok=True)
    os.makedirs(os.path.join(args.savedir, "val"), exist_ok=True)
    os.makedirs(os.path.join(args.savedir, "test"), exist_ok=True)
    np.random.seed(args.randomseed)

    for img_idx in tqdm(i_train):
        img_target = images[img_idx].to(device)
        pose_target = poses[img_idx, :3, :4].to(device)
        ray_origins, ray_directions = get_ray_bundle(H, W, focal, pose_target)
        coords = torch.stack(meshgrid_xy(torch.arange(H).to(device),
                                         torch.arange(W).to(device)), dim=-1)
        coords = coords.reshape((-1, 2))
        select_inds = np.random.choice(
            coords.shape[0], size=(args.num_random_rays), replace=False
        )
        select_inds = coords[select_inds]
        ray_origins = ray_origins[select_inds[:, 0], select_inds[:, 1], :]
        ray_directions = ray_directions[select_inds[:, 0], select_inds[:, 1], :]
        batch_rays = torch.stack([ray_origins, ray_directions], dim=0)
        target_s = img_target[select_inds[:, 0], select_inds[:, 1], :]

        cache_dict = {
            'height': H,
            'width': W,
            'focal_length': focal,
            'ray_bundle': batch_rays.detach().cpu(),
            'target': target_s.detach().cpu()
        }

        save_path = os.path.join(args.savedir, "train", str(img_idx).zfill(4) + '.data')
        torch.save(cache_dict, save_path)


    for img_idx in tqdm(i_val):
        img_target = images[img_idx].to(device)
        pose_target = poses[img_idx, :3, :4].to(device)
        ray_origins, ray_directions = get_ray_bundle(H, W, focal, pose_target)

        cache_dict = {
            'height': H,
            'width': W,
            'focal_length': focal,
            'ray_origins': ray_origins.detach().cpu(),
            'ray_directions': ray_directions.detach().cpu(),
            'target': img_target.detach().cpu()
        }

        save_path = os.path.join(args.savedir, "val", str(img_idx).zfill(4) + '.data')
        torch.save(cache_dict, save_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--datapath", type=str, required=True,
                        help="Path to root dir of dataset that needs caching.")
    parser.add_argument("--halfres", type=bool, default=True,
                        help="Whether to load the (Blender/synthetic) datasets"
                             "at half the resolution.")
    parser.add_argument("--stride", type=int, default=1,
                        help="Stride length. When set to k (k > 1), it samples"
                             "every kth sample from the dataset.")
    parser.add_argument("--savedir", type=str, required=True,
                        help="Path to save the cached dataset to.")
    parser.add_argument("--num-random-rays", type=int, default=8,
                        help="Number of random rays to sample per image.")
    parser.add_argument("--randomseed", type=int, default=3920,
                        help="Random seeed, for repeatability")
    args = parser.parse_args()

    cache_nerf_dataset(args)
