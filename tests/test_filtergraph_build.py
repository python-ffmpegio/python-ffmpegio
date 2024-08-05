from os import path
from tempfile import TemporaryDirectory
from ffmpegio import ffmpegprocess, filtergraph as fgb
from ffmpegio.filtergraph import Chain
from pprint import pprint
import pytest


@pytest.mark.parametrize(
    "left,right, from_left, to_right, chain_siso, ret",
    [
        # fmt: off
        ("scale", "fps",(0,0,0),(0,0,0),True,'scale,fps'),
        ("scale", "fps",(0,0,0),(0,0,0),False,'[UNC0]scale[L0];[L0]fps[UNC1]'),
        ("split", "fps",(0,0,1),(0,0,0),True,'[UNC0]split[UNC1][L0];[L0]fps[UNC2]'),
        ("split", "vstack",[(0,0,0),(0,0,1)],[(0,0,1),(0,0,0)],True,'[UNC0]split[L0][L1];[L1][L0]vstack[UNC1]'),
        ("scale", "fps,eq",(0,0,0),(0,0,0),True,'scale,fps,eq'),
        ("scale,fps", "eq",(0,1,0),(0,0,0),True,'scale,fps,eq'),
        ("scale", "[0:v]vstack[out]",(0,0,0),(0,0,1),True,'[UNC0]scale[L0];[0:v][L0]vstack[out]'),
        ("scale", "[in1][0:v]vstack[out]",(0,0,0),(0,0,0),True,'[UNC0]scale[in1];[in1][0:v]vstack[out]'),
        # fmt: on
    ],
)
def test_connect(left, right, from_left, to_right, chain_siso, ret):

    fg = fgb.connect(left, right, from_left, to_right, chain_siso)

    assert str(fg) == ret


@pytest.mark.parametrize(
    "left,right,how,n_links,strict,unlabeled_only,ret",
    [
        # fmt: off
        ("scale","fps",'all',0,False,False,'scale,fps'),
        ("split","vstack",'all',0,False,False,'[UNC0]split[L0][L1];[L0][L1]vstack[UNC1]'),
        ("split","vstack",'all',1,False,False,'[UNC0]split[L0][UNC2];[L0][UNC1]vstack[UNC3]'),
        # ("scale", "fps,eq",(0,0,0),(0,0,0),True,'scale,fps,eq'),
        # ("scale,fps", "eq",(0,1,0),(0,0,0),True,'scale,fps,eq'),
        # ("scale", "[0:v]vstack[out]",(0,0,0),(0,0,1),True,'[UNC0]scale[L0];[0:v][L0]vstack[out]'),
        # ("scale", "[in1][0:v]vstack[out]",(0,0,0),(0,0,0),True,'[UNC0]scale[in1];[in1][0:v]vstack[out]'),
        # fmt: on
    ],
)
def test_join(left, right, how, n_links, strict, unlabeled_only, ret):

    fg = fgb.join(left, right, how, n_links, strict, unlabeled_only)

    assert str(fg) == ret
