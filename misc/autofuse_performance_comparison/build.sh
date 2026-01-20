#!/bin/bash
set -e
CUR_DIR=$(dirname $(readlink -f $0))
TOP_DIR=${CUR_DIR}

rm -rf ${TOP_DIR}/build
cmake -S ${TOP_DIR} -B ${TOP_DIR}/build
cd ${TOP_DIR}/build
make -j$(nproc)