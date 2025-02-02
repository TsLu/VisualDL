# Copyright (c) 2021 VisualDL Authors. All Rights Reserve.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =======================================================================

import re
import json
from google.protobuf import text_format
from google.protobuf.json_format import MessageToDict

from visualdl.server.log import logger
from visualdl.proto import framework_pb2


def is_generate_var_list(var_list):
    """
    Determine whether the var lists are all generated var

    Args:
        var_list: the variable lists which model used

    Returns:
        True if the length of generated variable lists is equal to the variable we need, otherwise false.
    """
    flag = 0
    if not var_list:
        return False
    len_list = len(var_list)
    if isinstance(var_list, list):
        for each in var_list:
            if is_generate_var(each):
                flag += 1
    if flag == len_list:
        return True
    else:
        return False


def is_generate_var(var):
    """
    Determine whether one variable is generated var

    Args:
        var: the variable which model used

    Returns:
        True if variable is generated var
    """
    if re.match("_generated_var_[0-9]+", var) or \
       re.match("sequence_pool_[0-9]+.tmp_[0-9]+", var) or \
       re.match("cast_[0-9]+.tmp_[0-9]", var) or \
       re.match("learning_rate_[0-9]+", var) or \
       re.match("embedding_[0-9]+.tmp_[0-9]+", var):
        return True
    else:
        return False


def filter_generate_var(vars):
    """
    Filter variables which are generated var

    Args:
        vars: the variables which model used

    Returns:
        True if variables are generated var to fiter them
    """
    if "tail" in vars:
        if not vars["tail"] or "GRAD" in vars["tail"][0] or \
                (len(vars["tail"]) == 1 and re.match("cast_[0-9]+.tmp_[0-9]+", vars["tail"][0])):
            return True
    if len(vars["tail"]) == 1 and re.match("_generated_var_[0-9]+", vars["tail"][0]) or \
            len(vars["tail"]) == 1 and re.match("tmp_[0-9]+",  vars["tail"][0]):
        if len(vars["head"]) == 1:
            if is_generate_var(vars["head"][0]):
                return True
        else:
            if is_generate_var_list(vars["head"]):
                return True
    return False


def load_pbtxt_file(path):
    """
    Read network pbtxt

    Args:
        path: the model pbtxtfile

    Returns:
        None
    """
    with open(path, 'r') as fid:
        pbtxt_string = fid.read()
        pbtxt = framework_pb2.ProgramDesc()
        try:
            text_format.Merge(pbtxt_string, pbtxt)
        except text_format.ParseError:
            pbtxt.ParseFromString(pbtxt_string)
    return pbtxt


def get_network(stage, pbtxtfile):
    """
    Analysis network

    Args:
        stage: join or update stage
        pbtxtfile: the model pbtxtfile

    Returns:
        None
    """
    load_pbtxt = load_pbtxt_file(pbtxtfile)
    data = MessageToDict(load_pbtxt)
    blocks = data['blocks']
    vars_name_list = []
    ops_network_list = []
    for each in blocks:
        vars_list = each["vars"]
        ops_list = each["ops"]
        for vars in vars_list:
            var_name = vars["name"]
            if var_name not in vars_name_list:
                vars_name_list.append(var_name)
        i = 0
        for ops in ops_list:
            i += 1
            tmp = {}
            tmp["head"] = []
            tmp["tail"] = []
            if "inputs" not in ops or "outputs" not in ops:
                continue
            inputs = ops["inputs"]
            outputs = ops["outputs"]
            if ops["type"] in ["sequence_pool", "fused_seqpool_cvm", "elementwise_mul"] or "_grad" in ops["type"]:
                continue
            for input in inputs:
                if input["parameter"] != "X" and input["parameter"] != "Y" and input["parameter"] != "Input"\
                        or input["parameter"] == "Ids" or "seqpool_cvm" in input["arguments"] \
                        or "feed" in input["arguments"]:
                    continue
                else:
                    tmp["head"] = tmp["head"] + input["arguments"]
            if not tmp["head"]:
                continue
            for output in outputs:
                if output["parameter"] == "Out" or output["parameter"] == "Y":
                    tmp["tail"] = tmp["tail"] + output["arguments"]
            if len(tmp["head"]) >= 10:
                tmp["head"] = []
            if filter_generate_var(tmp):
                continue
            if len(tmp["tail"]) != 1:
                logger.info("node tail is not 1")
                continue
            else:
                tmp["name"] = tmp["tail"][0]
                tmp["tail"] = tmp["name"]
            logger.info("connections:{}".format(json.dumps(tmp)))
            ops_network_list.append(tmp)
    return ops_network_list


def save_network(network, stage):
    """
    Save network relationship to local file

    Args:
        network: the nwt work relations
        stage: join or update stage

    Returns:
        None
    """
    if not network:
        logger.error("network is null")
        return
    save_dir = "output/" + stage + "_" + "network.json"
    with open(save_dir, 'w') as f:
        json.dump(network, f)
        logger.info("save {} network relationship".format(stage))
