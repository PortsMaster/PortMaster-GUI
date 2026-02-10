# This file is for me to remember how to build xdelta/gptokeyb/gptokeyb2/sdl_resolution

# TODO: document the others.

# GPTOKEYB2 Compilation

```sh
DEVICE_ARCH="aarch64"
git clone "https://github.com/PortsMaster/gptokeyb2.git"
cd gptokeyb2
mkdir build
cd build
cmake ..
make
patchelf --replace-needed libinterpose.so libinterpose.$DEVICE_ARCH.so gptokeyb2
patchelf --set-soname libinterpose.$DEVICE_ARCH.so lib/libinterpose.so
mv lib/libinterpose.so libinterpose.$DEVICE_ARCH.so
mv gptokeyb2 gptokeyb2.$DEVICE_ARCH
```

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

## Compile innoextract statically.

This requires the static liblzma above to have been built and installed.

```sh
git clone "https://github.com/dscharrer/innoextract.git"

cd innoextract
mkdir build
cd build

cmake .. -DBZip2_USE_STATIC_LIBS=ON -DBoost_USE_STATIC_LIBS=ON -DLZMA_USE_STATIC_LIBS=ON -DUSE_LZMA=ON -DUSE_STATIC_LIBS=ON -DZLIB_USE_STATIC_LIBS=ON -Diconv_USE_STATIC_LIBS=ON

```

Even with all of the above the stupid thing wants to dynamically link to liblzma.so, so instead we manually edit `CMakeCache.txt`.

Find the following and edit so they match:

- `LZMA_INCLUDE_DIR:PATH=/usr/local/include`
- `LZMA_LIBRARY:FILEPATH=/usr/local/libliblzma.a`

Compile as normal:

```sh
make -j4
strip innoextract
```


## Compile xmlstartlet statically

```sh
# Install system libxslt, this stops it erroring out below
sudo apt install libxslt-dev

# Make sure we generate static libraries
export CFLAGS=-static
export CPPFLAGS=-static
export LDFLAGS=-static
export BUILDIR="$PWD"

# Static libxml2
git clone https://github.com/GNOME/libxml2.git

cd libxml2

./autogen.sh --without-python --enable-static=on
make

cd ..

# Static libxslt
git clone https://gitlab.gnome.org/GNOME/libxslt.git
cd libxslt

./autogen.sh --without-python --enable-static=on
make

# Fix a link issue
ln -s $PWD/libxslt/.libs/libxslt.a  libexslt/.libs/

cd ..

git clone git://git.code.sf.net/p/xmlstar/code --branch 1.6.1 --depth 1 xmlstar-code

# Its go time
cd xmlstar-code

autoreconf -sif

./configure \
        --prefix=/usr \
        --disable-build-docs \
        --with-libxml-prefix=/usr \
        --with-libxml-include-prefix=$BUILDIR/libxml2/include \
        --with-libxml-libs-prefix=$BUILDIR/libxml2/.libs \
        --with-libxslt-prefix=/usr \
        --with-libxslt-include-prefix=$BUILDIR/libxslt \
        --with-libxslt-libs-prefix=$BUILDIR/libxslt/libexslt/.libs \
        --enable-static-libs \
        LIBS="-lpthread"

# This caused so many headaches.
sed -i 's/ATTRIBUTE_UNUSED//g' "src/xml_pyx.c"

make

# DONE

```

It will error with `make[1]: *** No rule to make target 'doc/xmlstarlet.1', needed by 'all-am'.  Stop.` but it doesnt matter, the file we want is `xml`

Guidelines to build taken from here: https://github.com/acjohnson/xmlstarlet-static-binary

## Compile astcenc

```sh
git clone "https://github.com/bmdhacks/astc-encoder.git"

cd astc-encoder
git checkout bmd-guide
mkdir build
cd build

# compiler version and options were tested in an array of about 16 different options
CXX=clang++ cmake -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -mcpu=cortex-a35" \
      -DASTCENC_ISA_NEON=ON -DASTCENC_INVARIANCE=OFF \
      -DASTCENC_BLOCK_MAX_TEXELS=64 -DASTCENC_WERROR=OFF \
      -DCMAKE_INSTALL_PREFIX=../ ..
make install -j$(nproc)
```
