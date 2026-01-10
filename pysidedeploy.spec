[app]
title = sfplanner
project_dir = .
input_file = src/satisfactory_planner/main.py
project_file = 
exec_directory = .
icon = 

[python]
python_path = 
packages = Nuitka

[qt]
qml_files = 
excluded_qml_plugins = 

[nuitka]
extra_args = --quiet --noinclude-qt-translations --assume-yes-for-downloads --include-data-dir=src/satisfactory_planner/data=satisfactory_planner/data

[buildozer]
mode = 
recipe_dir = 
jars_dir = 
ndk_path = 
sdk_path = 
local_libs = 
arch = 