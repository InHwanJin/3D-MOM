#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

from pathlib import Path
import os, sys
from PIL import Image
import torch
import numpy as np
import tqdm
from argparse import ArgumentParser

import torch
import torch.nn as nn

class SceneFlow(nn.Module):
    def __init__(self, coord):
        super(SceneFlow, self).__init__()
        shape = coord.shape
        self.scene_flow = nn.Parameter(torch.zeros(shape, requires_grad=True))

    def forward(self):
	    return self.scene_flow


def flow2img(flow_uv, imtype=np.uint8):
    """
    Expects a two dimensional flow image of shape [H,W,2]
    According to the C++ source code of Daniel Scharstein
    According to the Matlab source code of Deqing Sun
    :param flow_uv: np.ndarray of shape [H,W,2]
    :param clip_flow: float, maximum clipping value for flow
    :param convert_to_bgr: bool, whether to change ordering and output BGR
    instead of RGB
    :return:
    """
    flow_uv = flow_uv.unsqueeze(0).detach().cpu()
    flow_uv = flow_to_color(flow_uv)
    flow_uv = flow_uv[0].permute(1,2,0).float().numpy()
    flow_numpy = np.clip(flow_uv, 0, 255)
    return flow_numpy.astype(imtype)

def flow_to_color(flow_uv, max_mag=None, clip_flow=None, convert_to_bgr=False):
    """
    Expects a two dimensional flow image of shape [H,W,2]
    According to the C++ source code of Daniel Scharstein
    According to the Matlab source code of Deqing Sun
    :param flow_uv: np.ndarray of shape [H,W,2]
    :param clip_flow: float, maximum clipping value for flow
    :param convert_to_bgr: bool, whether to change ordering and output BGR
    instead of RGB
    :return:
    """

    assert flow_uv.dim() == 4, f"input must have 4 dimensions. has {flow_uv.dim()}"
    assert flow_uv.shape[1] == 2, 'input flow must have shape [H,W,2]'

    flow_uv_permute = flow_uv.permute(0, 2, 3, 1)
    flow_uv_numpy = flow_uv_permute.view(flow_uv_permute.shape[0], flow_uv_permute.shape[1] * flow_uv_permute.shape[2],
                                         flow_uv_permute.shape[3]).cpu().numpy()

    if clip_flow is not None:
        flow_uv = np.clip(flow_uv, 0, clip_flow)

    u = flow_uv_numpy[:, :, 0]
    v = flow_uv_numpy[:, :, 1]

    rad = np.sqrt(np.square(u) + np.square(v))
    rad_max = np.max(rad)

    if max_mag is not None:
        rad_max = max_mag

    epsilon = 1e-5
    u = u / (rad_max + epsilon)
    v = v / (rad_max + epsilon)

    color = flow_compute_color(u, v, convert_to_bgr)
    color = torch.from_numpy(color).unsqueeze(0).view(flow_uv_permute.shape[0], flow_uv_permute.shape[1],
                                                      flow_uv_permute.shape[2], 3)
    color = color.permute(0, 3, 1, 2)
    return color

def flow_compute_color(u, v, convert_to_bgr=False):
    """
    Applies the flow color wheel to (possibly clipped) flow components u and v.
    According to the C++ source code of Daniel Scharstein
    According to the Matlab source code of Deqing Sun
    :param u: np.ndarray, input horizontal flow
    :param v: np.ndarray, input vertical flow
    :param convert_to_bgr: bool, whether to change ordering and output BGR instead of RGB
    :return:
    """

    flow_image = np.zeros((u.shape[0], u.shape[1], 3), np.uint8)

    colorwheel = make_colorwheel()  # shape [55x3]
    ncols = colorwheel.shape[0]

    rad = np.sqrt(np.square(u) + np.square(v))
    a = np.arctan2(-v, -u) / np.pi

    fk = (a + 1) / 2 * (ncols - 1)
    k0 = np.floor(fk).astype(np.int32)
    k1 = k0 + 1
    k1[k1 == ncols] = 1
    f = fk - k0

    for i in range(colorwheel.shape[1]):
        tmp = colorwheel[:, i]
        col0 = tmp[k0] / 255.0
        col1 = tmp[k1] / 255.0
        col = (1 - f) * col0 + f * col1

        idx = (rad <= 1)
        col[idx] = 1 - rad[idx] * (1 - col[idx])
        col[~idx] = col[~idx] * 0.75  # out of range?

        # Note the 2-i => BGR instead of RGB
        ch_idx = 2 - i if convert_to_bgr else i
        flow_image[:, :, ch_idx] = np.floor(255 * col)

    return flow_image

def make_colorwheel():
    """
    Generates a color wheel for optical flow visualization as presented in:
        Baker et al. "A Database and Evaluation Methodology for Optical Flow" (ICCV, 2007)
        URL: http://vision.middlebury.edu/flow/flowEval-iccv07.pdf
    According to the C++ source code of Daniel Scharstein
    According to the Matlab source code of Deqing Sun
    """

    RY = 15
    YG = 6
    GC = 4
    CB = 11
    BM = 13
    MR = 6

    ncols = RY + YG + GC + CB + BM + MR
    colorwheel = np.zeros((ncols, 3))
    col = 0

    # RY
    colorwheel[0:RY, 0] = 255
    colorwheel[0:RY, 1] = np.floor(255 * np.arange(0, RY) / RY)
    col = col + RY
    # YG
    colorwheel[col:col + YG, 0] = 255 - np.floor(255 * np.arange(0, YG) / YG)
    colorwheel[col:col + YG, 1] = 255
    col = col + YG
    # GC
    colorwheel[col:col + GC, 1] = 255
    colorwheel[col:col + GC, 2] = np.floor(255 * np.arange(0, GC) / GC)
    col = col + GC
    # CB
    colorwheel[col:col + CB, 1] = 255 - np.floor(255 * np.arange(CB) / CB)
    colorwheel[col:col + CB, 2] = 255
    col = col + CB
    # BM
    colorwheel[col:col + BM, 2] = 255
    colorwheel[col:col + BM, 0] = np.floor(255 * np.arange(0, BM) / BM)
    col = col + BM
    # MR
    colorwheel[col:col + MR, 2] = 255 - np.floor(255 * np.arange(MR) / MR)
    colorwheel[col:col + MR, 0] = 255
    return colorwheel

def save_image(image_numpy, image_path):
    image_pil = Image.fromarray(image_numpy)
    image_pil.save(image_path)

if __name__ == "__main__":
    torch.cuda.empty_cache()
    parser = ArgumentParser(description="Training script parameters")
    # Camera options
    # parser.add_argument('--input_dir', type=str, help='input folder that contains src images', required=True)
    parser.add_argument('--campath_gen', '-cg', type=str, default='lookdown', choices=['lookdown', 'lookaround', 'rotate360', 'hemisphere'], help='Camera extrinsic trajectories for scene generation')
    parser.add_argument('--campath_render', '-cr', type=str, default='llff', choices=['back_and_forth', 'llff', 'headbanging'], help='Camera extrinsic trajectories for video rendering')
    parser.add_argument('--input_dir', '-wf', type=str, help='input folder that contains src images', required=True)

    args = parser.parse_args(sys.argv[1:])
    
    trainData_dir = os.path.join(args.input_dir, 'Stage1')
    trainData_path = os.path.join(trainData_dir, 'TrainData.pth')
    train_data =torch.load(trainData_path)

    our_Flow_save_folder = os.path.join(trainData_dir,"3D_flow")
    os.makedirs(our_Flow_save_folder,exist_ok=True)

    T2C_Flow_save_folder = os.path.join(trainData_dir,"2D_flow")
    os.makedirs(T2C_Flow_save_folder,exist_ok=True)
    
    frames = train_data["frames"]

    for idx, frame in enumerate(frames):
        our_flow = frame["our_flow"][0]     #torch.Size([1, 2, 512, 512])
        viz_flow = flow2img(our_flow[0])
        our_flow_path = our_Flow_save_folder+'/'+str(idx).zfill(3)+'.png'
        save_image(viz_flow,our_flow_path)
    print("visualize our flow")


    for idx, frame in enumerate(frames):
        T2C_flow = frame['T2C_flow'][0]
        viz_flow = flow2img(T2C_flow[0])
        T2C_flow_path = T2C_Flow_save_folder+'/'+str(idx).zfill(3)+'.png'
        save_image(viz_flow,T2C_flow_path)
    print("visualize cinemagraphy flow")
    