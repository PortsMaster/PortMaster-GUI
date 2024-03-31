#!/bin/bash

# Directory where .pot file is located
POT_DIR="PortMaster/pylibs/locales"
POT_FILES=("messages" "themes")

cp PortMaster/pugwash{,.bak}

python3 tools/pm_release.py $*

awk -F"'" '/PORTMASTER_VERSION = / {print $2}' PortMaster/pugwash > PortMaster/version
cp PortMaster/version version

rm -vf PortMaster.zip

find . -iname '.DS_Store' -or -iname '._*' -delete -print

# for name in $(find . -iname '__pycache__');
# do
#     rm -fRv "$name"
# done

for lang_dir in $POT_DIR/* ; do
    LANG_CODE=$(basename "$lang_dir")
    if [[ "${LANG_CODE}" != "." ]] && [[ "${LANG_CODE}" != ".." ]] && [ -d "$lang_dir" ]; then
        # echo "${LANG_CODE}:"

        for POT_FILE in "${POT_FILES[@]}"; do

            LANG_POT_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.pot"
            LANG_PO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.po"
            LANG_MO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.mo"

            if [ -f "$LANG_POT_FILE" ]; then
                mv -fv "$LANG_POT_FILE" "$LANG_PO_FILE"
            fi

            # Compile .po file into .mo file
            # printf "msgfmt: "
            msgfmt -v -o "${LANG_MO_FILE}" "${LANG_PO_FILE}"

            # echo ""
        done
    fi
done

echo "Creating pylibs.zip"
cd PortMaster

rm -f pylibs.zip
zip -9r pylibs.zip exlibs/ pylibs/ \
    -x \*__pycache__\*/\* \
    -x \*.DS_Store \
    -x ._\* \
    -x \*NotoSans\*.ttf

cd ..

echo "Creating PortMaster.zip"
zip -9r PortMaster.zip PortMaster/ \
    -x PortMaster/pylibs/\* \
    -x PortMaster/exlibs/\* \
    -x PortMaster/config/\* \
    -x PortMaster/themes/\* \
    -x PortMaster/libs/\*.squashfs \
    -x PortMaster/libs/\*.squashfs.md5 \
    -x PortMaster/pugwash.bak \
    -x PortMaster/pugwash.txt \
    -x PortMaster/harbourmaster.txt \
    -x '*.DS_Store'

if [[ "$1" == "stable" ]]; then
    echo "Creating Installers"

    if [ ! -f "runtimes.zip" ]; then
        echo "Downloading Runtimes"
        # Download the runtimes
        mkdir -p runtimes
        cd runtimes
        for runtime_url in $(curl -s https://api.github.com/repos/PortsMaster/PortMaster-Runtime/releases/latest | grep browser_download_url | cut -d '"' -f 4); do
            if [[ "$runtime_url" =~ /zulu11.*$ ]]; then
                continue
            fi

            wget "$runtime_url"
        done

        # Validate them
        for check_file in *.md5; do
            runtime_file="${check_file/.md5/}"
            if [[ $(md5sum "${runtime_file}" | cut -d ' ' -f 1) != $(cat "${check_file}" | cut -d ' ' -f 1) ]]; then
                cd ..
                rm -fRv runtimes
                echo "Failed to validate runtime ${runtime_file}"
                exit 255
            fi
        done

        zip -9 ../runtimes.zip *
        cd ..
        rm -fRv runtimes
    fi

    if [ ! -d "makeself-2.5.0" ]; then
        echo "Downloading makeself"
        wget "https://github.com/megastep/makeself/releases/download/release-2.5.0/makeself-2.5.0.run"
        chmod +x makeself-2.5.0.run
        ./makeself-2.5.0.run
    fi

    echo "Building Release"
    mkdir -p pm_release
    cd pm_release
    cp ../PortMaster.zip .
    cp ../tools/installer.sh .
    cd ..

    # Remove old installers
    rm -f Install*PortMaster.sh

    makeself-2.5.0/makeself.sh --header "tools/makeself-header.sh" pm_release "Install.PortMaster.sh" "PortMaster Installer" ./installer.sh

    if [ -z "$NO_FULL_INSTALL" ]; then
        cd pm_release
        cp ../runtimes.zip .
        cd ..

        makeself-2.5.0/makeself.sh --header "tools/makeself-header.sh" pm_release "Install.Full.PortMaster.sh" "PortMaster Full Installer" ./installer.sh
    fi

    rm -fRv pm_release
fi

python3 tools/pm_version.py $*

# Restore this file
mv PortMaster/pugwash{.bak,}
