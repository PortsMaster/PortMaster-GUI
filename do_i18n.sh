#!/bin/bash

# Directory where .pot file is located
POT_DIR="PortMaster/pylibs/locales"
POT_FILES=("messages" "themes")
# Languages registered but not yet translated
NOT_WORKING=("da_DK" "fi_FI" "ja_JP" "nl_NL" "ko_KR")

for POT_FILE in "${POT_FILES[@]}"; do
    if [[ "$POT_FILE" == "messages" ]]; then
        echo "Extracting strings ${POT_FILE}"
        xgettext -v -o "${POT_DIR}/${POT_FILE}.pot" -L Python PortMaster/pugwash PortMaster/pylibs/harbourmaster/*.py PortMaster/pylibs/pug*.py

    elif [[ "$POT_FILE" == "themes" ]]; then
        echo "Extracting strings ${POT_FILE}"
        python3 theme_msgfmt.py
        # wget -O "${POT_DIR}/${POT_FILE}.pot" "https://github.com/PortsMaster/PortMaster-Themes/releases/latest/download/themes.pot"
    fi
done

crowdin upload

for POT_FILE in "${POT_FILES[@]}"; do
    # pygettext.py -d libharbourmaster -o pylibs/locales/harbourmaster.pot pylibs/harbourmaster
    # pygettext.py -d harbourmaster -o pylibs/locales/harbourmaster.pot harbourmaster

    # Iterate over subdirectories (languages) in the LC_MESSAGES folder
    for lang_dir in $POT_DIR/* ; do
        LANG_CODE=$(basename "$lang_dir")
        if [[ "${LANG_CODE}" != "." ]] && [[ "${LANG_CODE}" != ".." ]] && [ -d "$lang_dir" ]; then

            PO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.pot"
            MO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.mo"

            # Check if the .po file exists
            if [ -f "$PO_FILE" ]; then
                mkdir -p "$lang_dir/LC_MESSAGES"
                cp -v "${POT_DIR}/${POT_FILE}.pot" "${PO_FILE}"
            fi
        fi
    done
done

crowdin download

for BROKEN in "${NOT_WORKING[@]}"; do
    rm -fR "$POT_DIR/$BROKEN"
done

for lang_dir in $POT_DIR/* ; do
    LANG_CODE=$(basename "$lang_dir")
    if [[ "${LANG_CODE}" != "." ]] && [[ "${LANG_CODE}" != ".." ]] && [ -d "$lang_dir" ]; then
        echo "${LANG_CODE}:"

        for POT_FILE in "${POT_FILES[@]}"; do

            LANG_POT_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.pot"
            LANG_PO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.po"
            LANG_MO_FILE="$lang_dir/LC_MESSAGES/${POT_FILE}.mo"

            if [ -f "$LANG_POT_FILE" ]; then
                mv -fv "$LANG_POT_FILE" "$LANG_PO_FILE"
            fi

            # Compile .po file into .mo file
            printf "msgfmt: "
            msgfmt -v -o "${LANG_MO_FILE}" "${LANG_PO_FILE}"

            echo ""
        done
    fi
done
