/*
 * -------------------------------------------------------------------------
 * This file is part of the MindStudio project.
 * Copyright (c) 2026 Huawei Technologies Co.,Ltd.
 *
 * MindStudio is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *
 *          http://license.coscl.org.cn/MulanPSL2
 *
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
 * EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
 * MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
 * See the Mulan PSL v2 for more details.
 * -------------------------------------------------------------------------
 */
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>

#include "ge/ge_api.h"
#include "graph/ascend_string.h"
#include "graph/graph.h"
#include "log_manager.h"

using namespace ge;

void ExecuteGraph(const std::string &graphPath, const std::vector<uint8_t *> &inputsData,
                  const std::vector<std::vector<int64_t>> &inputsShape, const std::vector<int> &inputsDtype,
                  const std::vector<uint8_t *> &outputsData)
{
    Graph graph("graph");
    graph.LoadFromFile(graphPath.c_str());
    std::map<AscendString, AscendString> options;
    Session session(options);
    session.AddGraph(1, graph, options);
    // create inputs
    std::vector<Tensor> inputs;
    for (size_t i = 0; i < inputsData.size(); i++)
    {
        auto dtype = static_cast<DataType>(inputsDtype[i]);
        TensorDesc desc(Shape(inputsShape[i]), FORMAT_ND, dtype);
        int64_t dataSize = 1;
        for (int indexShape = 0; indexShape < int(inputsShape[i].size()); indexShape++)
        {
            dataSize *= inputsShape[i][indexShape];
        }
        dataSize *= GetSizeByDataType(dtype);
        inputs.emplace_back(desc, inputsData[i], dataSize);
    }
    // execute graph
    std::vector<Tensor> outputs;
    auto ret = session.RunGraph(1, inputs, outputs);
    if (ret != SUCCESS)
    {
        ERROR("RunGraph failed, the error code is %d, the graphPath is %s", ret, graphPath.c_str());
    }
}

void ExecuteGraphWrapper(const std::string &graphPath, const std::vector<pybind11::array> &inputsData,
                         const std::vector<std::vector<int64_t>> &inputsShape, const std::vector<int> &inputsDtype,
                         const std::vector<pybind11::array> &outputsData)
{
    pybind11::gil_scoped_release release;
    std::vector<uint8_t *> inputsPtr;
    for (const auto &inputData : inputsData)
    {
        auto buf = inputData.request();
        inputsPtr.push_back(static_cast<uint8_t *>(buf.ptr));
    }
    std::vector<uint8_t *> outputsPtr;
    for (const auto &outputData : outputsData)
    {
        auto buf = outputData.request();
        outputsPtr.push_back(static_cast<uint8_t *>(buf.ptr));
    }
    ExecuteGraph(graphPath, inputsPtr, inputsShape, inputsDtype, outputsPtr);
}

PYBIND11_MODULE(ExecuteGraph_C, m)
{
    m.doc() = "ExecuteGraph Python binding";
    m.def("execute_graph", &ExecuteGraphWrapper, "Execute computational graph", pybind11::arg("graph_path"),
          pybind11::arg("inputs_data"), pybind11::arg("inputs_shape"), pybind11::arg("inputs_dtype"),
          pybind11::arg("outputs_data"));
}
