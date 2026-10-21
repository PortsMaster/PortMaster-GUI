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

# PORTMSG Compilation

Message cards for `pm_message`/`pm_show_error`. Needs `libsdl2-dev` and `xxd`; the aarch64 build only needs GLIBC_2.17.

```sh
git clone "https://github.com/PortsMaster/portmsg.git"
cd portmsg
make
cp portmsg.aarch64 ../PortMaster/
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

## Compile libtheoradec (libs.aarch64/libtheoradec.so.1)

Distro builds (Debian's `libtheora0`) have the debugging telemetry on, which needs
`libcairo.so.2`: most CFWs don't have it, so the library won't load at all. This one
needs only libc (GLIBC_2.17). Built on a Raspberry Pi with Debian 11.

```sh
curl -fsSLO https://downloads.xiph.org/releases/ogg/libogg-1.3.5.tar.xz
curl -fsSLO https://downloads.xiph.org/releases/theora/libtheora-1.1.1.tar.bz2
sha256sum libogg-1.3.5.tar.xz libtheora-1.1.1.tar.bz2
# c4d91be36fc8e54deae7575241e03f4211eb102afb3fc0775fbbc1b740016705  libogg-1.3.5.tar.xz
# b6ae1ee2fa3d42ac489287d3ec34c5885730b1296f0801ae577a35193d3affbc  libtheora-1.1.1.tar.bz2

P=$PWD/prefix
tar xf libogg-1.3.5.tar.xz && tar xf libtheora-1.1.1.tar.bz2

# libogg is only needed for its headers, libtheoradec doesn't link it.
cd libogg-1.3.5
./configure --prefix=$P --disable-static && make -j$(nproc) && make install
cd ..

# The 2009 configure script doesn't know aarch64: give it the build triplet.
cd libtheora-1.1.1
PKG_CONFIG_PATH=$P/lib/pkgconfig ./configure --build=aarch64-unknown-linux-gnu --prefix=$P \
  --with-ogg=$P --disable-static --disable-telemetry --disable-examples --disable-oggtest \
  --disable-vorbistest --disable-sdltest --disable-spec CFLAGS="-O2 -g0"
make -j$(nproc) && make install
cd ..

strip --strip-unneeded -o libtheoradec.so.1 $P/lib/libtheoradec.so.1.1.4
readelf -d libtheoradec.so.1 | grep NEEDED    # only libc.so.6
```
