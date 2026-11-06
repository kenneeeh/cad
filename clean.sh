#!/bin/bash

# Define the target directory
TARGET_DIR="no_backup"

# Remove everything within the target directory
rm -rf "${TARGET_DIR:?}"/*

# Create a new folder called output_files within the target directory
mkdir "${TARGET_DIR}/output_files"

mkdir "${TARGET_DIR}/output_netlists"
