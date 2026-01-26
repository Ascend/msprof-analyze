/*
 * Copyright (c) 2026, Huawei Technologies Co., Ltd.
 * All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <string>
#include "graph/ascend_string.h"
#include "graph/graph.h"
#include "ge/ge_api.h"
#include "log_manager.h"

using namespace ge;

void ExecuteGraph(const std::string &graphPath, const std::vector<uint8_t *> &inputsData,
    const std::vector<std::vector<int64_t>> &inputsShape,
    const std::vector<int> &inputsDtype, const std::vector<uint8_t *> &outputsData)
{
    Graph graph("graph");
    graph.LoadFromFile(graphPath.c_str());
    std::map<AscendString, AscendString> options_initializer;
    auto ret = GEInitialize(options_initializer);
    if (ret != SUCCESS) {
        ERROR("GEInitialize failed, the error code is %d, the graphPath is %s", ret, graphPath.c_str());
    }
    std::map<AscendString, AscendString> options;
    Session session(options);
    session.AddGraph(1, graph, options);
    // create inputs
    std::vector<Tensor> inputs;
    for (size_t i = 0; i < inputsData.size(); i++) {
        auto dtype = static_cast<DataType>(inputsDtype[i]);
        TensorDesc desc(Shape(inputsShape[i]), FORMAT_ND, dtype);
        int64_t dataSize = 1;
        for (int indexShape = 0; indexShape < int(inputsShape[i].size()); indexShape++) {
            dataSize *= inputsShape[i][indexShape];
        }
        dataSize *= GetSizeByDataType(dtype);
        inputs.emplace_back(desc, inputsData[i], dataSize);
    }
    // execute graph
    std::vector<Tensor> outputs;
    ret = session.RunGraph(1, inputs, outputs);
    if (ret != SUCCESS) {
        ERROR("RunGraph failed, the error code is %d, the graphPath is %s", ret, graphPath.c_str());
    }
    ret = GEFinalize();
    if (ret != SUCCESS) {
        ERROR("GEFinalize failed, the error code is %d, the graphPath is %s", ret, graphPath.c_str());
    }
}

void ExecuteGraphWrapper(const std::string &graphPath, const std::vector<pybind11::array> &inputsData,
    const std::vector<std::vector<int64_t>> &inputsShape,
    const std::vector<int> &inputsDtype, const std::vector<pybind11::array> &outputsData)
{
    pybind11::gil_scoped_release release;
    std::vector<uint8_t *> inputsPtr;
    for (const auto &inputData : inputsData) {
        auto buf = inputData.request();
        inputsPtr.push_back(static_cast<uint8_t *>(buf.ptr));
    }
    std::vector<uint8_t *> outputsPtr;
    for (const auto &outputData : outputsData) {
        auto buf = outputData.request();
        outputsPtr.push_back(static_cast<uint8_t *>(buf.ptr));
    }
    ExecuteGraph(graphPath, inputsPtr, inputsShape, inputsDtype, outputsPtr);
}

PYBIND11_MODULE(ExecuteGraph_C, m) {
    m.doc() = "ExecuteGraph Python binding";
    m.def("execute_graph", &ExecuteGraphWrapper, "Execute computational graph",
        pybind11::arg("graph_path"),
        pybind11::arg("inputs_data"),
        pybind11::arg("inputs_shape"),
        pybind11::arg("inputs_dtype"),
        pybind11::arg("outputs_data")
    );
}