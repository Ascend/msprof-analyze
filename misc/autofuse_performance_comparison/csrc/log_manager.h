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
#pragma once
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <sys/syscall.h>

#define FILENAME (strrchr("/" __FILE__, '/') + 1)
#define DEBUG(format, ...) do {                                           \
            printf("[DEBUG] [%s:%d] " format "\n",   \
            FILENAME, __LINE__, ##__VA_ARGS__);            \
    } while (0)

#define INFO(format, ...) do {                                           \
            printf("[INFO] [%s:%d] " format "\n",    \
            FILENAME, __LINE__, ##__VA_ARGS__);            \
    } while (0)

#define WARNING(format, ...) do {                                           \
            printf("[WARNING] [%s:%d] " format "\n", \
            FILENAME, __LINE__, ##__VA_ARGS__);            \
    } while (0)

#define ERROR(format, ...) do {                                           \
            printf("[ERROR] [%s:%d] " format "\n",   \
            FILENAME, __LINE__, ##__VA_ARGS__);            \
    } while (0)
