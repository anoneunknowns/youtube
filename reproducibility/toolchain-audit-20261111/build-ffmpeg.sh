#!/bin/sh
set -eu
project_root=/Users/support/codex/youtube
build_root="$project_root/.venv/toolchain-build"
install_prefix=/Users/support/.local/share/youtube-toolchain/ffmpeg/9.0.2
cd "$build_root"
printf '%s  %s\n' 8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e ffmpeg-9.0.2.tar.xz | shasum -a 256 -c -
test "$(git -C x264 rev-parse HEAD)" = b35605ace3ddf7c1a5d67a2eb553f034aef41d55
cd x264
./configure --prefix="$install_prefix" --enable-static --disable-cli --enable-pic --disable-opencl > "$build_root/x264-configure.log" 2>&1
make -j4 > "$build_root/x264-build.log" 2>&1
make install > "$build_root/x264-install.log" 2>&1
cd "$build_root"
if [ ! -d ffmpeg-9.0.2 ]; then tar -xf ffmpeg-9.0.2.tar.xz; fi
cd ffmpeg-9.0.2
PKG_CONFIG_PATH="$install_prefix/lib/pkgconfig" ./configure --prefix="$install_prefix" --enable-gpl --enable-libx264 --enable-static --disable-shared --disable-autodetect --enable-zlib --enable-videotoolbox --enable-audiotoolbox --enable-securetransport --disable-ffplay --disable-doc --disable-debug --pkg-config-flags=--static > "$build_root/ffmpeg-configure.log" 2>&1
make -j4 > "$build_root/ffmpeg-build.log" 2>&1
make install > "$build_root/ffmpeg-install.log" 2>&1
ln -sfn "$install_prefix/bin/ffmpeg" "$project_root/.venv/bin/ffmpeg"
ln -sfn "$install_prefix/bin/ffprobe" "$project_root/.venv/bin/ffprobe"
"$install_prefix/bin/ffmpeg" -version
"$install_prefix/bin/ffprobe" -version
