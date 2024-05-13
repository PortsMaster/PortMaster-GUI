# This file is for me to remember how to build xdelta/gptokeyb/gptokeyb2/sdl_resolution

# TODO: document the others.

# XDELTA3 Compilation

## Compile liblzma statically
```sh
./configure --enable-static=yes --enable-shared=no
make -j4
sudo make install
```

## Compile xdelta3 statically with liblzma

```sh
git clone "https://github.com/jmacd/xdelta.git"
cd xdelta
git checkout release3_1_apl
wget https://patch-diff.githubusercontent.com/raw/jmacd/xdelta/pull/241.diff
git apply 241.diff
cd xdelta3

./generate_build_files.sh
LDFLAGS=-L/usr/local/lib/ CXXFLAGS=-I/usr/local/include ./configure --with-liblzma
make -j4
strip xdelta3
```
