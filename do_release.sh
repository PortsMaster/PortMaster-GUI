#!/bin/bash

# Directory where .pot file is located
POT_DIR="PortMaster/pylibs/locales"
POT_FILES=("messages" "themes")

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
zip -9r pylibs.zip exlibs/ pylibs/ -x '*__pycache__*/*' -x '*.DS_Store'

cd ..

echo "Creating PortMaster.zip"
zip -9r PortMaster.zip PortMaster/ \
    -x PortMaster/pylibs/\* \
    -x PortMaster/exlibs/\* \
    -x PortMaster/config/\* \
    -x PortMaster/themes/\* \
    -x PortMaster/libs/\*.squashfs \
    -x PortMaster/libs/\*.squashfs.md5 \
    -x PortMaster/pugwash.txt \
    -x PortMaster/harbourmaster.txt \
    -x '*.DS_Store'

