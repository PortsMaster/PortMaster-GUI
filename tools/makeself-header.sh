cat << EOF  > "$archname"
#!/bin/bash
# This script was generated using Makeself $MS_VERSION
# The license covering this archive and its contents, if any, is wholly independent of the Makeself license (GPL)
# PORTMASTER: restore.portmaster.zip, Restore PortMaster.sh

exec > >(tee -a "\$HOME/portmaster.log") 2>&1
exec > >(tee -a "\$HOME/portmaster.log") 2>&1

ORIG_UMASK=\`umask\`
if test "$KEEP_UMASK" = n; then
    umask 077
fi

CRCsum="$CRCsum"
MD5="$MD5sum"
SHA="$SHAsum"
SIGNATURE="$Signature"

# This is a modification so that we don't crash on various handhelds with a tiny /tmp directory.
if [ -d "/roms2/ports/" ]; then
  TMPROOT="/roms2/ports"
elif [ -d "/userdata/roms/ports" ]; then
  TMPROOT="/userdata/roms/ports"
elif [ -d "/roms/ports/" ]; then
  TMPROOT="/roms/ports"
else
  TMPROOT=\${TMPDIR:=/tmp}
fi

USER_PWD="\$PWD"
export USER_PWD
ARCHIVE_DIR=\`dirname "\$0"\`
export ARCHIVE_DIR

label="$LABEL"
script="$SCRIPT"
scriptargs="$SCRIPTARGS"
cleanup_script="${CLEANUP_SCRIPT}"
licensetxt="$LICENSE"
helpheader="${HELPHEADER}"
targetdir="$archdirname"
filesizes="$filesizes"
totalsize="$totalsize"
keep="$KEEP"
nooverwrite="$NOOVERWRITE"
quiet="n"
accept="n"
nodiskspace="n"
export_conf="$EXPORT_CONF"
decrypt_cmd="$DECRYPT_CMD"
skip="$SKIP"

print_cmd_arg=""
if type printf > /dev/null; then
    print_cmd="printf"
elif test -x /usr/ucb/echo; then
    print_cmd="/usr/ucb/echo"
else
    print_cmd="echo"
fi

if test -d /usr/xpg4/bin; then
    PATH=/usr/xpg4/bin:\$PATH
    export PATH
fi

if test -d /usr/sfw/bin; then
    PATH=\$PATH:/usr/sfw/bin
    export PATH
fi

unset CDPATH

MS_Printf()
{
    \$print_cmd \$print_cmd_arg "\$1"
}

MS_PrintLicense()
{
  PAGER=\${PAGER:=more}
  if test x"\$licensetxt" != x; then
    PAGER_PATH=\`exec <&- 2>&-; which \$PAGER || command -v \$PAGER || type \$PAGER\`
    if test -x "\$PAGER_PATH"; then
      echo "\$licensetxt" | \$PAGER
    else
      echo "\$licensetxt"
    fi
    if test x"\$accept" != xy; then
      while true
      do
        MS_Printf "Please type y to accept, n otherwise: "
        read yn
        if test x"\$yn" = xn; then
          keep=n
          eval \$finish; exit 1
          break;
        elif test x"\$yn" = xy; then
          break;
        fi
      done
    fi
  fi
}

MS_diskspace()
{
	(
	df -k "\$1" | tail -1 | awk '{ if (\$4 ~ /%/) {print \$3} else {print \$4} }'
	)
}

MS_dd()
{
    blocks=\`expr \$3 / 1024\`
    bytes=\`expr \$3 % 1024\`
    # Test for ibs, obs and conv feature
    if dd if=/dev/zero of=/dev/null count=1 ibs=512 obs=512 conv=sync 2> /dev/null; then
        dd if="\$1" ibs=\$2 skip=1 obs=1024 conv=sync 2> /dev/null | \\
        { test \$blocks -gt 0 && dd ibs=1024 obs=1024 count=\$blocks ; \\
          test \$bytes  -gt 0 && dd ibs=1 obs=1024 count=\$bytes ; } 2> /dev/null
    else
        dd if="\$1" bs=\$2 skip=1 2> /dev/null
    fi
}

MS_dd_Progress()
{
    if test x"\$noprogress" = xy; then
        MS_dd "\$@"
        return \$?
    fi
    file="\$1"
    offset=\$2
    length=\$3
    pos=0
    bsize=4194304
    while test \$bsize -gt \$length; do
        bsize=\`expr \$bsize / 4\`
    done
    blocks=\`expr \$length / \$bsize\`
    bytes=\`expr \$length % \$bsize\`
    (
        dd ibs=\$offset skip=1 count=1 2>/dev/null
        pos=\`expr \$pos \+ \$bsize\`
        MS_Printf "     0%% " 1>&2
        if test \$blocks -gt 0; then
            while test \$pos -le \$length; do
                dd bs=\$bsize count=1 2>/dev/null
                pcent=\`expr \$length / 100\`
                pcent=\`expr \$pos / \$pcent\`
                if test \$pcent -lt 100; then
                    MS_Printf "\b\b\b\b\b\b\b" 1>&2
                    if test \$pcent -lt 10; then
                        MS_Printf "    \$pcent%% " 1>&2
                    else
                        MS_Printf "   \$pcent%% " 1>&2
                    fi
                fi
                pos=\`expr \$pos \+ \$bsize\`
            done
        fi
        if test \$bytes -gt 0; then
            dd bs=\$bytes count=1 2>/dev/null
        fi
        MS_Printf "\b\b\b\b\b\b\b" 1>&2
        MS_Printf " 100%%  " 1>&2
    ) < "\$file"
}

MS_Help()
{
    cat << EOH >&2
Makeself version $MS_VERSION
 1) Getting help or info about \$0 :
  \$0 --help   Print this message
  \$0 --info   Print embedded info : title, default target directory, embedded script ...
  \$0 --lsm    Print embedded lsm entry (or no LSM)
  \$0 --list   Print the list of files in the archive
  \$0 --check  Checks integrity of the archive
  \$0 --verify-sig key Verify signature agains a provided key id

 2) Running \$0 :
  \$0 [options] [--] [additional arguments to embedded script]
  with following options (in that order)
  --confirm             Ask before running embedded script
  --quiet               Do not print anything except error messages
  --accept              Accept the license
  --noexec              Do not run embedded script (implies --noexec-cleanup)
  --noexec-cleanup      Do not run embedded cleanup script
  --keep                Do not erase target directory after running
                        the embedded script
  --noprogress          Do not show the progress during the decompression
  --nox11               Do not spawn an xterm
  --nochown             Do not give the target folder to the current user
  --chown               Give the target folder to the current user recursively
  --nodiskspace         Do not check for available disk space
  --target dir          Extract directly to a target directory (absolute or relative)
                        This directory may undergo recursive chown (see --nochown).
  --tar arg1 [arg2 ...] Access the contents of the archive through the tar command
  --ssl-pass-src src    Use the given src as the source of password to decrypt the data
                        using OpenSSL. See "PASS PHRASE ARGUMENTS" in man openssl.
                        Default is to prompt the user to enter decryption password
                        on the current terminal.
  --cleanup-args args   Arguments to the cleanup script. Wrap in quotes to provide
                        multiple arguments.
  --                    Following arguments will be passed to the embedded script\${helpheader}
EOH
}

# This function extracts, DECOMPRESSES, executes, and cleans up the embedded framebuffer helper.
MS_Extract_And_Run_FB_Helper()
{
    local message="\$1"

    # This only works on aarch64 currently.
    if [ ! -e /lib/ld-linux-aarch64.so.1 ] && [ ! -e /lib64/ld-linux-aarch64.so.1 ]; then
        return 1
    fi

    # Use the TMPROOT defined at the start of the makeself script
    local helper_dir="\$TMPROOT/makeself_helper_$$"
    local helper_bin="\$helper_dir/fb_msg"
    local temp_b64="\$helper_dir/data.b64" # Path for the temporary base64 file

    mkdir -p "\$helper_dir"
    if [ ! -d "\$helper_dir" ]; then
        return 1
    fi

    # Use a trap to ensure cleanup even if the script exits
    trap "rm -rf '\$helper_dir'" RETURN

    # NOTE: The data is decompressed with gunzip after being decoded from base64.
    (
        # Embeded fb_msg program for aarch64
        echo "H4sICPG7hWgCA2ZiX21zZwDtGm1wVNX1vH2bzSZZ1wQCrATkJSDCjiwbVIi4DckGjGhwkETbUTu7L8lbdmU/4u7CBIhLUH441R/ZEgWmgqjVgbQ/6AhTmLEl"
        echo "oM0w1XFS0EinQENQoWIdHD5kW7Pbc9+7N7n7zBrttP1TbvL23HPu+b733XffvW/Tsob7DIIArIjwWyDYwUINr6H0rvIRFqRVQQH+lsFUMCFu5Pj08LqQDc0j"
        echo "djS5KoOG62EZZEOBg3mQu+yflA2ZJPklvu6brlH3TReyYC+1e8yQLWegcr1UrpfxUzhIHRvUxWekVxPVp4dLIRsaKVz5abyV1PdPpHHoYCtkQyb3MMqZ4PuX"
        echo "YgpXUXu58rKS+ssg64f5wUDz/GDrvGAgvLZ9nixHW/wL73LEIo5KzadS2sf1Dz0CfU/vO7Bsw6PvPTHzrSfti+r6HhefmWGkPgiUh42JfC77AmfvhxQRiuBY"
        echo "/lj0KeCXsjWStE4YQ8fUHHQhB/1pvKQx6PV4VYxBJ7wlY9AX59D/aA76XTnoO3L4Y87Bb81Bn5eDvieH/iU5+G/PQYc2JRqNREFujkTjEArJbRCLR4NKGHxt"
        echo "a+MxRFqRAQKRlngQQmvDhKElGIkpEGlTmaKBcNwHHk9Lu+zxBcJyMLBBQRSHZ4snFpejcU9IDoSB4GR4LoT6huXuOs8CR+Ui8CxvWuFB/crqQCyuRJtW1AUj"
        echo "YaVJbg4SFatDkTBV4dFYx2QEOk8Y1LnCMPKXTRPwz8/dd9uSL5lISxSy7zuR3tD9RRo8qKN3UvqeGTq6lcrp6EDpJ3X0fjpRsfuB0Rm+j/ILRm3+Y+UgR+dv"
        echo "sV6Obuboxzi6haMPcvTirBuDzrtGbT4YGbcc3cjPYxydfy7YODrvp8TRCzj6HI5eyNGdHL2Io1dxdD6uGo5+E0e/n6NbOfpKjn4zR/8JR+fnCS9H5++n4Y2H"
        echo "9w6LkDwG0D288cieXtEzQOiXkN6F3VmSrk8VDy1JSoYZAzMk8SN2YVt/iaEmVWwAtU3FTYhXcHgh4m4OtyLezOETEH+Gwycj/hqHT0X8KIffivgQh1cQ+8Io"
        echo "PpvY53A7sc/hDmKfwxcQ+xo+vPFXah4uNwp7rz5u2Pt1i7g3NRNS+MB5ymKApk7MRQXUpDCLXTBYnypfuTiJvZb6PJPZdid0rhoUJ9ovN9airBtl61C2JjW8"
        echo "8SOWzy7oX5xcZKxJ1SLvEZS5IoIddVfKIjRtRd0qz5XFSXz+dcWG6lPdu1xJGfPbg7wEajruTb6JuBfxIXFKz1mxtOePFCd1nDO63AddyT/wMh/em9yB+MeZ"
        echo "zJTrLUJy6FkhKfQ+d7wXaYPaY6ALOn+U7Ca4WGp/DeH7yDskGpMEr0XeA0i7jP7uTmfuHryz9tAnSL8WqTmUB53HZ2I8zXgNJMiSq/P4WXFyz06ia76au99s"
        echo "xqWLasNWnTyPes9NbJiLcqsMeAlq3mw9H+DYG8R41qBc6scNc89h3QidEw48CQ+X3wwPEp4DCaFxSJxkL+8QGl9H/vKZpodfewBKSBvhJXS877taMP5fEH3z"
        echo "SU4m9yRoXEGE29D+dPTxVrw+FQHzh3mcCcnPsN9J/8IX9alnEbZcqE9tQbjlw/rUYyin4KW2f1KfwvXp/p+iHtKv/P2A7f3QKyQx3v5yhPg8u9iLsSO+r/xk"
        echo "fUpGuUui0AM41oisnh+Xye9VfLPpRK1l8/Pl39RuPYL8z6Cs+1J9qlmVNYzIEnvDG3+vjdciSOH46fcerb2nRoC7VT9P1acQ7ldt3FWTKkf/T+IlYb69R4V7"
        echo "LheRsXl0Dx/DKYxps+H6IqO55tArIKyZi2PeQHALwQ1r9grQZLTVzc2Tag65wVRkOllzqByMRb/sEBvdHaaycrOxzIj3w+FOeApjbXrWX36Q6G92PXDC+0Tj"
        echo "iZZpdSfc/rLGmjvALoJox/b262jTPw0mbIJbop9jfwzmd64yC51T1fHybnXyoijYvxAN9r+LRrvZYn4+H/vtS4zh5sDqqp8L+UUFWO8VCh4cnNs71SvCIhxY"
        echo "JUvK0X4m03TeCMmMBF+9ms40ET/GksH+WXhOvMk+JE6wy0JB0aBY2HMY88T0HEmP6hGwzuZHNmd+hf4Pb3x7ZN64gr5eFsUeMn9cQ9+v4kXmka8xtusYQ4uh"
        echo "5p53AO7m54nhje+qOjfNgadexbx126HkqjjZHjNB8grqP4tj/hPRhj6W2sk9cqACSt5CH0nuLqLeC2qO8uzn0fYD2B/zQCzyCPlrXkBdRO/fRLMdnxulBB4W"
        echo "zGuCSMeYSr5WfdfiOCsW2EnM50QL2slHO0U9T6ONw0LBmju0XJYQnb8e5nMwGnc3jrnuoYVJEveLWD9wdGGy2zDpvWs4Z2jxCxi/oac7Xbe1NZ3ZFhfIa0nn"
        echo "cTLuXt8Quz6E9zCJ9yzGN4ixe2HJwCuGiRdx3DaNlSsix/cD8+mRmLxaWSzdFpMqVigxgkjxiNQaiLUF5fUVhTC/VVk339fshDo5HI7EJbISlHxROaQ0r/X5"
        echo "lKiE7YEWxSEt1UQC4dVEgbaUdBRCof0HlkKw29GdQmjyB2JSSF4vxeU1ihRT1ilROSiF8B0orsQc0sqgIscUqVmR2uR4QAnHHbCMrG6lqCK3Ei94JwNhXyQa"
        echo "Qr5ImHLh2rZNz6WFQtwPKaFIdP3IAz+x+Y3Nv9uxOZHI/CXzzvlMIphOpzuqcClVXNWhVlQA/3ZxuXe88cYOt8vl3ozF7bLNwop7lo1BcPl8PpcNC1ZcufXY"
        echo "XAkbKwmXDUYqFpvTRlZO+Gtzcgsum8WSRcipF42DDdALFQ+m8Y/QE7s7ChM2gL4+czG2VTU0+ZsaqsDp9Kp8qNtJDI/Y8bkyLqICvUKFVLnqQGLUGDaYkNvb"
        echo "i2H3DXyGAduq1EAQJw0qnGZCumWaK5i2WCDh9XYQ3IWQJChhUi2TtKkJw59qk8mlKVcNq9BJrGiJSagOYJ1IanZATXtinRftkwrGh8rJP9K9Xi/qbQ9iRoLt"
        echo "qn2vN0Ghl7SHiV2fKuYDrVcSYDWZTCo92N6GsuBVSwL6vkwP9PX1Qd9n1858gJB0N+EjxjR9Pt+6apOV4EQO9btIvLS3wUf5NWDD7ugbSH+J+vqCVUHUR0cP"
        echo "pNW0psHlJMUFvSR6kwguCykuKJ6zlO/2DDazEWqq9lWDml6MH4gHaM+EVEytiicwT9MWOttJ3gGqSca17sD4bUA6EPnBYiJ+e72YAIxD7VYb6Zcv0gMDfQg1"
        echo "ftAGvIZjBqg+K8FJPhDHBHRAcXFHcfEE0n8+6ocWPw7IgQF1hCKmDjif6g/2szp+LDZbmw373aYOAxsQBEmqXafF5eP3IMrEe4lB8j4y7Wom046L2SfwQdCO"
        echo "+AsI8ZkB7yPcTdrxAfMuee9BeAphN8JLZB8qlcmUolw/wgaEDf/IZPYjfB/hBWH0nUzYsAqM7bcKZZYZKo0EcupaJuPk9pHuIPt7SHNxextk/28W+nA/IdRa"
        echo "pZ3GXaJ7q+GhM6dPqK8/pXQPayXyGHX7UmpnIj3O6cN1PryMtF5CeMxavNOwS1h15rQV3FqdLID3k/cyjK9Ds1mz07wr373V1J1X96LxJbFum2G7cH/hmdMf"
        echo "n/xo4MSHVqgl+ZtDOprYZHLLNX1uK5w+c59WX0HsEN0kfszNy5e1HKGNfsNO+665y7bO6b79xdkv3bZt1vaZOypWopE/Z1nB25jknLx05PRvGfGvcdQ9LRfP"
        echo "ocyp69k5ulFulBvlRrlRbpQb5f+rsHMBdg7ATrP8FLK9aHb+xfagt9BN51t05w1lkH1uORWyzx2m6dqvpjMRArfT80C2595JFyjsrOAgbWd76UcpZHvobBE/"
        echo "6VtndFq5MGP0/FVde9FASynO9vSnsPNpUzb9ubxsv81UvkBn/58ZLR7Gmqa4n8pnKM7yfInibtqeorjpv9Tf7Jy50/o9BazZ5zvjlcH8/w1k50r1dXWLpTlL"
        echo "leaAHJYqnY4Fjsp5C+fSmrTAuaDSWVmJi2VHzB+LR+NyMzgC4bgSbQNHOBJXHKvDax3NawPB1nmBVkqqdS+fF5dXg9rml2N+cLSuD8fWhzQYj2ot65RojOy1"
        echo "8IgH26JKUCaMtNYWjBOTAfyNK+3460ME2yKtclwGh+L3qNszHn9rdBTTJDxyNCqv1yRYHRXLoUALWo3E1R/NgKasORYDR0skFFLC8f/QeCmiY3XkvsnxXQXo"
        echo "vqvgz8PzOXn9dwuzdPz695LZOvl2QzaUxpEn73H4Khlh8myeYZDNR3m6eYmVapoDg24eYvCYMDpPiZw8mw/uo3SDbl5j8Og4+XuIzhlMns0TDM7W+W/Qwcfp"
        echo "HMRwNg8xyPJnorb18T9Jc2rQzYMj86Ewdv5Y/HEq79bNqwxWcfKTx5BPcN/a8M8hBkvH6f/1Onn9PHIpx3csrGzRybN5kMH9ed8t/zOdPHtuMlg8jv9duvuv"
        echo "25oNp+d99/jZrpPP9f1PLvtv6uRtpdnwZeHb34PwZR99hIi6dQL7PsgMY8sz+DZo59iibh1x8HvKH+PuTf75x76/GhSy1xlmXT/+icbP5HfTdcTuGfQcfhz7"
        echo "Azp5tg65QOU7x5H/q06ePff80nfHz8qnlMbk26h8Ww55/fj5nNL0G+hM/vYc8jwUx3iubKPyl8ex/y+i782JUCgAAA=="
    ) > "\$temp_b64"

    # Now, decode and decompress from the well-formed temporary file.
    # We add an 'if !' check for better error handling.
    if ! base64 -d < "\$temp_b64" | gunzip -c > "\$helper_bin"; then
        echo "Error: Failed to decode/decompress embedded helper binary." >&2
        return 1
    fi

    if [ -s "\$helper_bin" ]; then
        chmod +x "\$helper_bin"
        # Execute the helper in the background so it doesn't block the installer
        "\$helper_bin" "\$message" >/dev/null 2>&1 &
    else
        echo "Failed to decode/decompress embedded helper binary." >&2
        return 1
    fi

    return 0
}

# This is the main display function. It calls the helper as a last resort.
MS_Handheld_Display()
{
    local message="\$1"

    # 1. Check if we are in an interactive shell (like SSH or serial)
    if [ -t 1 ]; then
        MS_Printf "\n\$message. Please be patient, this may take a while.\n"
    fi

    # 2. NEW: Check for Zenity (best for Retrodeck/desktop environments)
    # The global variable ZPID must be declared outside this function.
    if type zenity >/dev/null 2>&1; then
        zenity --progress --pulsate \
            --title="PortMaster Installer" \
            --text="\$message" \
            --info-text="Please be patient, this may take several minutes..." \
            --no-cancel --auto-close --width=400 &
        ZPID=\$! # Store the background process PID in our global variable
        return 0
    fi

    # 3. Check for 'foot' terminal (for high-level Sway/Weston environments)
    if type foot >/dev/null 2>&1; then
        foot -F /bin/bash -c "printf '\n\n\n   %s\n\n   This may take a while.\n' \"\$message\"; while true; do sleep 1; done" &
        ZPID=\$! # Store the background process PID in our global variable
        return 0
    fi

    # 4. Check for a console that is a real text-mode display (KMS/DRM + fbcon).
    # This now iterates through all reported active consoles (e.g., "ttyFIQ0 tty0")
    # and writes to the first one that is available.
    if [ -e "/dev/dri/card0" ] && [ -e /sys/class/tty/console/active ]; then
        local displayed=0
        for tty_name in \$(cat /sys/class/tty/console/active 2>/dev/null); do
            # Check if this specific tty device exists and is writable
            if [ -w "/dev/\$tty_name" ]; then
                (
                    printf "\033c" # ANSI reset/clear screen
                    printf "\n\n************************************************\n"
                    printf   "** %s\n" "\$message"
                    printf   "** Please be patient, this may take a while.  \n"
                    printf   "************************************************\n"
                ) > "/dev/\$tty_name"
                displayed=1
                # We found a writable console, no need to check others.
                break
            fi
        done

        if [ "\$displayed" -eq 1 ];
            then return 0;
        fi
    fi

    # 5. LAST RESORT: For non-DRM systems with a framebuffer, run our binary.
    if [ -w "/dev/fb0" ]; then
        MS_Extract_And_Run_FB_Helper "\$message"
        return 0
    fi

    # Oh well.
    return 1
}

MS_Verify_Sig()
{
    GPG_PATH=\`exec <&- 2>&-; which gpg || command -v gpg || type gpg\`
    MKTEMP_PATH=\`exec <&- 2>&-; which mktemp || command -v mktemp || type mktemp\`
    test -x "\$GPG_PATH" || GPG_PATH=\`exec <&- 2>&-; which gpg || command -v gpg || type gpg\`
    test -x "\$MKTEMP_PATH" || MKTEMP_PATH=\`exec <&- 2>&-; which mktemp || command -v mktemp || type mktemp\`
	offset=\`head -n "\$skip" "\$1" | wc -c | sed "s/ //g"\`
    temp_sig=\`mktemp -t XXXXX\`
    echo \$SIGNATURE | base64 --decode > "\$temp_sig"
    gpg_output=\`MS_dd "\$1" \$offset \$totalsize | LC_ALL=C "\$GPG_PATH" --verify "\$temp_sig" - 2>&1\`
    gpg_res=\$?
    rm -f "\$temp_sig"
    if test \$gpg_res -eq 0 && test \`echo \$gpg_output | grep -c Good\` -eq 1; then
        if test \`echo \$gpg_output | grep -c \$sig_key\` -eq 1; then
            test x"\$quiet" = xn && echo "GPG signature is good" >&2
        else
            echo "GPG Signature key does not match" >&2
            exit 2
        fi
    else
        test x"\$quiet" = xn && echo "GPG signature failed to verify" >&2
        exit 2
    fi
}

MS_Check()
{
    OLD_PATH="\$PATH"
    PATH=\${GUESS_MD5_PATH:-"\$OLD_PATH:/bin:/usr/bin:/sbin:/usr/local/ssl/bin:/usr/local/bin:/opt/openssl/bin"}
	MD5_ARG=""
    MD5_PATH=\`exec <&- 2>&-; which md5sum || command -v md5sum || type md5sum\`
    test -x "\$MD5_PATH" || MD5_PATH=\`exec <&- 2>&-; which md5 || command -v md5 || type md5\`
    test -x "\$MD5_PATH" || MD5_PATH=\`exec <&- 2>&-; which digest || command -v digest || type digest\`
    PATH="\$OLD_PATH"

    SHA_PATH=\`exec <&- 2>&-; which shasum || command -v shasum || type shasum\`
    test -x "\$SHA_PATH" || SHA_PATH=\`exec <&- 2>&-; which sha256sum || command -v sha256sum || type sha256sum\`

    if test x"\$quiet" = xn; then
		MS_Printf "Verifying archive integrity..."
    fi
    offset=\`head -n "\$skip" "\$1" | wc -c | sed "s/ //g"\`
    fsize=\`cat "\$1" | wc -c | sed "s/ //g"\`
    if test \$totalsize -ne \`expr \$fsize - \$offset\`; then
        echo " Unexpected archive size." >&2
        exit 2
    fi
    verb=\$2
    i=1
    for s in \$filesizes
    do
		crc=\`echo \$CRCsum | cut -d" " -f\$i\`
		if test -x "\$SHA_PATH"; then
			if test x"\`basename \$SHA_PATH\`" = xshasum; then
				SHA_ARG="-a 256"
			fi
			sha=\`echo \$SHA | cut -d" " -f\$i\`
			if test x"\$sha" = x0000000000000000000000000000000000000000000000000000000000000000; then
				test x"\$verb" = xy && echo " \$1 does not contain an embedded SHA256 checksum." >&2
			else
				shasum=\`MS_dd_Progress "\$1" \$offset \$s | eval "\$SHA_PATH \$SHA_ARG" | cut -b-64\`;
				if test x"\$shasum" != x"\$sha"; then
					echo "Error in SHA256 checksums: \$shasum is different from \$sha" >&2
					exit 2
				elif test x"\$quiet" = xn; then
					MS_Printf " SHA256 checksums are OK." >&2
				fi
				crc="0000000000";
			fi
		fi
		if test -x "\$MD5_PATH"; then
			if test x"\`basename \$MD5_PATH\`" = xdigest; then
				MD5_ARG="-a md5"
			fi
			md5=\`echo \$MD5 | cut -d" " -f\$i\`
			if test x"\$md5" = x00000000000000000000000000000000; then
				test x"\$verb" = xy && echo " \$1 does not contain an embedded MD5 checksum." >&2
			else
				md5sum=\`MS_dd_Progress "\$1" \$offset \$s | eval "\$MD5_PATH \$MD5_ARG" | cut -b-32\`;
				if test x"\$md5sum" != x"\$md5"; then
					echo "Error in MD5 checksums: \$md5sum is different from \$md5" >&2
					exit 2
				elif test x"\$quiet" = xn; then
					MS_Printf " MD5 checksums are OK." >&2
				fi
				crc="0000000000"; verb=n
			fi
		fi
		if test x"\$crc" = x0000000000; then
			test x"\$verb" = xy && echo " \$1 does not contain a CRC checksum." >&2
		else
			sum1=\`MS_dd_Progress "\$1" \$offset \$s | CMD_ENV=xpg4 cksum | awk '{print \$1}'\`
			if test x"\$sum1" != x"\$crc"; then
				echo "Error in checksums: \$sum1 is different from \$crc" >&2
				exit 2
			elif test x"\$quiet" = xn; then
				MS_Printf " CRC checksums are OK." >&2
			fi
		fi
		i=\`expr \$i + 1\`
		offset=\`expr \$offset + \$s\`
    done
    if test x"\$quiet" = xn; then
		echo " All good."
    fi
}

MS_Decompress()
{
    if test x"\$decrypt_cmd" != x""; then
        { eval "\$decrypt_cmd" || echo " ... Decryption failed." >&2; } | eval "$GUNZIP_CMD"
    else
        eval "$GUNZIP_CMD"
    fi
    
    if test \$? -ne 0; then
        echo " ... Decompression failed." >&2
    fi
}

UnTAR()
{
    if test x"\$quiet" = xn; then
		tar \$1vf - $UNTAR_EXTRA 2>&1 || { echo " ... Extraction failed." >&2; kill -15 \$$; }
    else
		tar \$1f - $UNTAR_EXTRA 2>&1 || { echo Extraction failed. >&2; kill -15 \$$; }
    fi
}

MS_exec_cleanup() {
    if test x"\$cleanup" = xy && test x"\$cleanup_script" != x""; then
        cleanup=n
        cd "\$tmpdir"
        eval "\"\$cleanup_script\" \$scriptargs \$cleanupargs"
    fi
}

MS_cleanup()
{
    echo 'Signal caught, cleaning up' >&2
    if [ -n "\$ZPID" ]; then
        kill \$ZPID 2>/dev/null
    fi

    MS_exec_cleanup
    cd "\$TMPROOT"
    rm -rf "\$tmpdir"
    eval \$finish; exit 15
}

finish=true
xterm_loop=
noprogress=$NOPROGRESS
nox11=$NOX11
copy=$COPY
ownership=$OWNERSHIP
verbose=n
cleanup=y
cleanupargs=
sig_key=
ZPID=""

initargs="\$@"

while true
do
    case "\$1" in
    -P* | --controllers* | --core* | --emulator*)
    shift
    ;;
    -h | --help)
	MS_Help
	exit 0
	;;
    -q | --quiet)
	quiet=y
	noprogress=y
	shift
	;;
	--accept)
	accept=y
	shift
	;;
    --info)
	echo Identification: "\$label"
	echo Target directory: "\$targetdir"
	echo Uncompressed size: $USIZE KB
	echo Compression: $COMPRESS
	if test x"$ENCRYPT" != x""; then
	    echo Encryption: $ENCRYPT
	fi
	echo Date of packaging: $DATE
	echo Built with Makeself version $MS_VERSION
	echo Build command was: "$MS_COMMAND"
	if test x"\$script" != x; then
	    echo Script run after extraction:
	    echo "    " \$script \$scriptargs
	fi
	if test x"$copy" = xcopy; then
		echo "Archive will copy itself to a temporary location"
	fi
	if test x"$NEED_ROOT" = xy; then
		echo "Root permissions required for extraction"
	fi
	if test x"$KEEP" = xy; then
	    echo "directory \$targetdir is permanent"
	else
	    echo "\$targetdir will be removed after extraction"
	fi
	exit 0
	;;
    --dumpconf)
	echo LABEL=\"\$label\"
	echo SCRIPT=\"\$script\"
	echo SCRIPTARGS=\"\$scriptargs\"
    echo CLEANUPSCRIPT=\"\$cleanup_script\"
	echo archdirname=\"$archdirname\"
	echo KEEP=$KEEP
	echo NOOVERWRITE=$NOOVERWRITE
	echo COMPRESS=$COMPRESS
	echo filesizes=\"\$filesizes\"
    echo totalsize=\"\$totalsize\"
	echo CRCsum=\"\$CRCsum\"
	echo MD5sum=\"\$MD5sum\"
	echo SHAsum=\"\$SHAsum\"
	echo SKIP=\"\$skip\"
	exit 0
	;;
    --lsm)
cat << EOLSM
EOF
eval "$LSM_CMD"
cat << EOF  >> "$archname"
EOLSM
	exit 0
	;;
    --list)
	echo Target directory: \$targetdir
	offset=\`head -n "\$skip" "\$0" | wc -c | sed "s/ //g"\`
	for s in \$filesizes
	do
	    MS_dd "\$0" \$offset \$s | MS_Decompress | UnTAR t
	    offset=\`expr \$offset + \$s\`
	done
	exit 0
	;;
	--tar)
	offset=\`head -n "\$skip" "\$0" | wc -c | sed "s/ //g"\`
	arg1="\$2"
    shift 2 || { MS_Help; exit 1; }
	for s in \$filesizes
	do
	    MS_dd "\$0" \$offset \$s | MS_Decompress | tar "\$arg1" - "\$@"
	    offset=\`expr \$offset + \$s\`
	done
	exit 0
	;;
    --check)
	MS_Check "\$0" y
	exit 0
	;;
    --verify-sig)
    sig_key="\$2"
    shift 2 || { MS_Help; exit 1; }
    MS_Verify_Sig "\$0"
    ;;
    --confirm)
	verbose=y
	shift
	;;
	--noexec)
	script=""
    cleanup_script=""
	shift
	;;
    --noexec-cleanup)
    cleanup_script=""
    shift
    ;;
    --keep)
	keep=y
	shift
	;;
    --target)
	keep=y
	targetdir="\${2:-.}"
    shift 2 || { MS_Help; exit 1; }
	;;
    --noprogress)
	noprogress=y
	shift
	;;
    --nox11)
	nox11=y
	shift
	;;
    --nochown)
	ownership=n
	shift
	;;
    --chown)
        ownership=y
        shift
        ;;
    --nodiskspace)
	nodiskspace=y
	shift
	;;
    --xwin)
	if test "$NOWAIT" = n; then
		finish="echo Press Return to close this window...; read junk"
	fi
	xterm_loop=1
	shift
	;;
    --phase2)
	copy=phase2
	shift
	;;
	--ssl-pass-src)
	if test x"$ENCRYPT" != x"openssl"; then
	    echo "Invalid option --ssl-pass-src: \$0 was not encrypted with OpenSSL!" >&2
	    exit 1
	fi
	decrypt_cmd="\$decrypt_cmd -pass \$2"
    shift 2 || { MS_Help; exit 1; }
	;;
    --cleanup-args)
    cleanupargs="\$2"
    shift 2 || { MS_Help; exit 1; }
    ;;
    --)
	shift
	break ;;
    -*)
	echo Unrecognized flag : "\$1" >&2
	MS_Help
	exit 1
	;;
    *)
	break ;;
    esac
done

if test x"\$quiet" = xy -a x"\$verbose" = xy; then
	echo Cannot be verbose and quiet at the same time. >&2
	exit 1
fi

if test x"$NEED_ROOT" = xy -a \`id -u\` -ne 0; then
	echo "Administrative privileges required for this archive (use su or sudo)" >&2
	exit 1	
fi

if test x"\$copy" \!= xphase2; then
    MS_PrintLicense
fi

case "\$copy" in
copy)
    tmpdir="\$TMPROOT"/makeself.\$RANDOM.\`date +"%y%m%d%H%M%S"\`.\$\$
    mkdir "\$tmpdir" || {
	echo "Could not create temporary directory \$tmpdir" >&2
	exit 1
    }
    SCRIPT_COPY="\$tmpdir/makeself"
    echo "Copying to a temporary location..." >&2
    cp "\$0" "\$SCRIPT_COPY"
    chmod +x "\$SCRIPT_COPY"
    cd "\$TMPROOT"
    export USER_PWD="\$tmpdir"
    exec "\$SCRIPT_COPY" --phase2 -- \$initargs
    ;;
phase2)
    finish="\$finish ; rm -rf \`dirname \$0\`"
    ;;
esac

if test x"\$nox11" = xn; then
    if test -t 1; then  # Do we have a terminal on stdout?
	:
    else
        if test x"\$DISPLAY" != x -a x"\$xterm_loop" = x; then  # No, but do we have X?
            if xset q > /dev/null 2>&1; then # Check for valid DISPLAY variable
                GUESS_XTERMS="xterm gnome-terminal rxvt dtterm eterm Eterm xfce4-terminal lxterminal kvt konsole aterm terminology"
                for a in \$GUESS_XTERMS; do
                    if type \$a >/dev/null 2>&1; then
                        XTERM=\$a
                        break
                    fi
                done
                chmod a+x \$0 || echo Please add execution rights on \$0 >&2
                if test \`echo "\$0" | cut -c1\` = "/"; then # Spawn a terminal!
                    exec \$XTERM -e "\$0 --xwin \$initargs"
                else
                    exec \$XTERM -e "./\$0 --xwin \$initargs"
                fi
            fi
        fi
    fi
fi

MS_Handheld_Display "Installing \$(basename \$0)."

if test x"\$targetdir" = x.; then
    tmpdir="."
else
    if test x"\$keep" = xy; then
	if test x"\$nooverwrite" = xy && test -d "\$targetdir"; then
            echo "Target directory \$targetdir already exists, aborting." >&2
            exit 1
	fi
	if test x"\$quiet" = xn; then
	    echo "Creating directory \$targetdir" >&2
	fi
	tmpdir="\$targetdir"
	dashp="-p"
    else
	tmpdir="\$TMPROOT/selfgz\$\$\$RANDOM"
	dashp=""
    fi
    mkdir \$dashp "\$tmpdir" || {
	echo 'Cannot create target directory' \$tmpdir >&2
	echo 'You should try option --target dir' >&2
	eval \$finish
	exit 1
    }
fi

location="\`pwd\`"
if test x"\$SETUP_NOCHECK" != x1; then
    MS_Check "\$0"
fi
offset=\`head -n "\$skip" "\$0" | wc -c | sed "s/ //g"\`

if test x"\$verbose" = xy; then
	MS_Printf "About to extract $USIZE KB in \$tmpdir ... Proceed ? [Y/n] "
	read yn
	if test x"\$yn" = xn; then
		eval \$finish; exit 1
	fi
fi

if test x"\$quiet" = xn; then
    # Decrypting with openssl will ask for password,
    # the prompt needs to start on new line
	if test x"$ENCRYPT" = x"openssl"; then
	    echo "Decrypting and uncompressing \$label..."
	else
        MS_Printf "Uncompressing \$label"
	fi
fi
res=3
if test x"\$keep" = xn; then
    trap MS_cleanup 1 2 3 15
fi

if test x"\$nodiskspace" = xn; then
    leftspace=\`MS_diskspace "\$tmpdir"\`
    if test -n "\$leftspace"; then
        if test "\$leftspace" -lt $USIZE; then
            echo
            echo "Not enough space left in "\`dirname \$tmpdir\`" (\$leftspace KB) to decompress \$0 ($USIZE KB)" >&2
            echo "Use --nodiskspace option to skip this check and proceed anyway" >&2
            if test x"\$keep" = xn; then
                echo "Consider setting TMPDIR to a directory with more free space."
            fi
            eval \$finish; exit 1
        fi
    fi
fi

for s in \$filesizes
do
    if MS_dd_Progress "\$0" \$offset \$s | MS_Decompress | ( cd "\$tmpdir"; umask \$ORIG_UMASK ; UnTAR xp ) 1>/dev/null; then
		if test x"\$ownership" = xy; then
			(cd "\$tmpdir"; chown -R \`id -u\` .;  chgrp -R \`id -g\` .)
		fi
    else
		echo >&2
		echo "Unable to decompress \$0" >&2
		eval \$finish; exit 1
    fi
    offset=\`expr \$offset + \$s\`
done
if test x"\$quiet" = xn; then
	echo
fi

cd "\$tmpdir"
res=0
if test x"\$script" != x; then
    if test x"\$export_conf" = x"y"; then
        MS_BUNDLE="\$0"
        MS_LABEL="\$label"
        MS_SCRIPT="\$script"
        MS_SCRIPTARGS="\$scriptargs"
        MS_ARCHDIRNAME="\$archdirname"
        MS_KEEP="\$KEEP"
        MS_NOOVERWRITE="\$NOOVERWRITE"
        MS_COMPRESS="\$COMPRESS"
        MS_CLEANUP="\$cleanup"
        export MS_BUNDLE MS_LABEL MS_SCRIPT MS_SCRIPTARGS
        export MS_ARCHDIRNAME MS_KEEP MS_NOOVERWRITE MS_COMPRESS
    fi

    if test x"\$verbose" = x"y"; then
		MS_Printf "OK to execute: \$script \$scriptargs \$* ? [Y/n] "
		read yn
		if test x"\$yn" = x -o x"\$yn" = xy -o x"\$yn" = xY; then
			eval "\"\$script\" \$scriptargs \"\\\$@\""; res=\$?;
		fi
    else
		eval "\"\$script\" \$scriptargs \"\\\$@\""; res=\$?
    fi
    if test "\$res" -ne 0; then
		test x"\$verbose" = xy && echo "The program '\$script' returned an error code (\$res)" >&2
    fi
fi

if [ -n "\$ZPID" ]; then
    kill \$ZPID 2>/dev/null
fi

MS_exec_cleanup

if test x"\$keep" = xn; then
    cd "\$TMPROOT"
    rm -rf "\$tmpdir"
fi
eval \$finish; exit \$res
EOF
