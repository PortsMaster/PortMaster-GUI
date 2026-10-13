# SPDX-License-Identifier: MIT
#
# PortMasterGUI FifoControlMixin.

import json
import os
from pathlib import Path
from pugwash import tasks
from loguru import logger
from pugwash.scenes import DialogSelectionList
from gettext import gettext as _


class FifoControlMixin:
    """
    PortMasterGUI methods: fifo_control: shell scripts drive the GUI through a named pipe (see PortMasterDialog.txt).
    """

    ## Fifo Control
    def fifo_reg_set_info(self, fifo_config, args):
        if len(args) < 3:
            fifo_config['done-file'].write_text("FAIL")
            return

        reg_name, key_name, *info_data = args
        key_info = fifo_config["register"].setdefault(reg_name, {}).setdefault(key_name, {})
        for info_datum in info_data:
            if ':' not in info_datum:
                continue

            info_key, info_value = info_datum.split(':', 1)
            key_info[info_key] = info_value

        fifo_config['done-file'].write_text("DONE")

    def fifo_reg_clear_info(self, fifo_config, args):
        if len(args) < 2:
            fifo_config['done-file'].write_text("FAIL")
            return

        reg_name, key_name, value = args[:2]
        register = fifo_config["register"].setdefault(reg_name, {})
        if key_name in register:
            del register[key_name]

        fifo_config['done-file'].write_text("DONE")

    def fifo_reg_clear(self, fifo_config, args):
        if len(args) < 1:
            fifo_config['done-file'].write_text("FAIL")
            return

        reg_name = args[0]
        if reg_name in fifo_config["register"]:
            del fifo_config["register"][reg_name]

        fifo_config['done-file'].write_text("DONE")

    def fifo_reg_dump(self, fifo_config, args):
        if len(args) < 1:
            fifo_config['done-file'].write_text("FAIL")
            return

        reg_name = args[0]
        if reg_name in fifo_config["register"]:
            fifo_config['done-file'].write_text(json.dumps(fifo_config["register"][reg_name]))

        else:
            fifo_config['done-file'].write_text("FAIL")

    def fifo_selection_list(self, fifo_config, args):
        config = {
            'want_cancel': False,
            'want_description': False,
            'want_images': False,
            'ok_text': _("Okay"),
            'cancel_text': _("Cancel"),
            }

        register = None

        i = 0
        while i < len(args):
            if not args[i].startswith('--'):
                i += 1
                continue

            if args[i] == '--':
                del args[i]
                break

            if args[i].startswith('--cancel-text='):
                config['ok_text'] = _(args[i].split('=', 1)[-1])
                del args[i]

            elif args[i].startswith('--ok-text='):
                config['ok_text'] = _(args[i].split('=', 1)[-1])
                del args[i]

            elif args[i].startswith('--register='):
                reg_name = args[i].split('=', 1)[-1]
                register = fifo_config['register'].get(reg_name, {})
                del args[i]

            elif args[i].startswith('--want-description'):
                config['want_description'] = True
                del args[i]

            elif args[i].startswith('--want-images'):
                config['want_images'] = True
                del args[i]

            else:
                logger.warning(f"unknown option {args[i]}")
                del args[i]

        ## This fixes a bug :D
        self.events.handle_events()

        with self.enable_cancellable(False):
            selection_list = DialogSelectionList(self, config, register)
            self.push_scene('selection_list', selection_list)

            try:
                while True:
                    if self.events.was_pressed('A'):
                        temp = selection_list.selected_option()
                        logger.debug(temp)
                        fifo_config['done-file'].write_text(str(temp))
                        return

                    if config['want_cancel'] and self.events.was_pressed('B'):
                        fifo_config['done-file'].write_text("CANCEL")
                        return

                    self.do_loop()

            finally:
                self.pop_scene()

        fifo_config['done-file'].write_text("FAIL")

    def fifo_messages_begin(self, fifo_config, args):
        if self.message_box_depth > 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        self.messages_begin(internal=True)
        fifo_config['done-file'].write_text("DONE")

    def fifo_messages_end(self, fifo_config, args):
        if self.message_box_depth == 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        self.messages_end(internal=True)
        fifo_config['done-file'].write_text("DONE")

    def fifo_message(self, fifo_config, args):
        if len(args) == 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        # Not sure how I never noticed that newlines were displaying as "\n" ...
        self.message(args[0].replace('\\n', '\n'))
        fifo_config['done-file'].write_text("DONE")

    def fifo_progress(self, fifo_config, args):
        if len(args) == 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        amount = 0
        total = 100
        fmt = None

        if len(args) > 3 and args[3] in ('data', '%'):
            total = args[3]

        if len(args) > 2 and args[2].isnumeric():
            total = int(args[2])

        if len(args) > 1 and args[1].isnumeric():
            amount = int(args[1])

        if amount > total:
            total, amount = amount, total

        if total == 0:
            total = 100

        self.progress(args[0], amount, total, fmt)

        fifo_config['done-file'].write_text("DONE")

    def fifo_progress_clear(self, fifo_config, args):
        self.progress(None, None, None)
        fifo_config['done-file'].write_text("DONE")

    def fifo_message_box(self, fifo_config, args):
        """
        message_box
        """
        mb_config = {
            "want_cancel": False,
            }

        if len(args) == 0:
            fifo_config['done-file'].write_text("TRUE")
            return

        i = 0
        while i < len(args):
            if not args[i].startswith('--'):
                i += 1
                continue

            if args[i] == '--':
                del args[i]
                break

            if args[i] == '--want-cancel':
                mb_config['want_cancel'] = True
                del args[i]
                continue

            if len(args) > 1:
                if args[i] == '--cancel-text':
                    mb_config['cancel_text'] = _(args[i + 1])
                    del args[i]
                    continue

                elif args[i] == '--ok-text':
                    mb_config['ok_text'] = _(args[i + 1])
                    del args[i]
                    continue

            logger.warning(f"unknown option {args[i]}")
            del args[i]

        if len(args) == 0:
            fifo_config['done-file'].write_text("TRUE")
            return

        fifo_config['done-file'].write_text("WAIT")
        result = self.message_box(args[0].replace('\\n', '\n'), **mb_config)
        fifo_config['done-file'].write_text(result and "TRUE" or "FALSE")

    def fifo_check_runtime(self, fifo_config, args):
        if self.hm is None:
            logger.debug("runtime install requested with no harbourmaster.")
            fifo_config['done-file'].write_text("FAIL")
            return

        if len(args) == 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        ## Always answer, the shell script waits until the done file changes.
        result = 255
        try:
            with self.enable_messages():
                with self.enable_cancellable(False):
                    result = self.run_task(self.hm.check_runtime, args[0])

        except Exception:
            logger.exception(f"fifo: check_runtime {args[0]} failed")

        finally:
            fifo_config['done-file'].write_text(result == 0 and "OKAY" or "FAIL")

    def fifo_install(self, fifo_config, args):
        if self.hm is None:
            logger.debug("port install requested with no harbourmaster.")
            fifo_config['done-file'].write_text("FAIL")
            return

        if len(args) == 0:
            fifo_config['done-file'].write_text("FAIL")
            return

        ## Always answer, the shell script waits until the done file changes. A cancelled
        ## install (CancelEvent is swallowed by enable_cancellable) leaves result as a failure.
        result = 255
        try:
            with self.enable_messages():
                with self.enable_cancellable(False):
                    with self.disable_messagebox():
                        result = self.run_task(self.hm.install_port, args[0])
                        logger.debug(f"result: {result}")

        except Exception:
            logger.exception(f"fifo: install {args[0]} failed")

        finally:
            fifo_config['done-file'].write_text(result == 0 and "OKAY" or "FAIL")

    fifo_commands = {
        'register_set_info': fifo_reg_set_info,
        'register_clear_info': fifo_reg_clear_info,
        'register_clear': fifo_reg_clear,
        'register_dump': fifo_reg_dump,

        'selection_list': fifo_selection_list,

        'messages_begin': fifo_messages_begin,
        'messages_end': fifo_messages_end,
        'message': fifo_message,

        'progress': fifo_progress,
        'progress_clear': fifo_progress_clear,

        'message_box': fifo_message_box,
        'check_runtime': fifo_check_runtime,
        'install': fifo_install,
        }

    def do_fifo_control(self, config, argv):
        """
        {command} fifo_control /dev/shm/portmaster/pg_input /dev/shm/portmaster/pg_done > /dev/null &

        printf "begin_messages" | sudo tee /dev/shm/portmaster/pg_input > /dev/null
        printf "message\1Words go here mate." | sudo tee /dev/shm/portmaster/pg_input > /dev/null
        printf "end_messages" | sudo tee /dev/shm/portmaster/pg_input > /dev/null
        printf "message_box\1with_false\1This is a message you might want to display." | sudo tee /dev/shm/portmaster/hm_input > /dev/null

        """
        if len(argv[1]) < 2:
            return 0

        logger.info("-- Beginning Fifo Control --")

        fifo_file = Path(argv[0])
        done_file = Path(argv[1])

        if fifo_file.exists():
            fifo_file.unlink()

        if done_file.exists():
            done_file.unlink()

        fifo_config = {
            'fifo-file': fifo_file,
            'done-file': done_file,
            'register': {},
            }

        self.cancellable = False
        reader = None

        try:
            os.mkfifo(fifo_file, mode=0o777)

            reader = tasks.FifoReader(fifo_file)
            done_file.write_text("DONE")

            while True:
                args = reader.get()

                if args is None:
                    self.do_loop()
                    continue

                args = args.strip("\1").split("\1")

                done_file.write_text("WAIT")

                if args[0] == 'exit':
                    done_file.write_text("DONE")
                    return 0

                if args[0].lower() in self.fifo_commands:
                    self.fifo_commands[args[0].lower()](self, fifo_config, args[1:])

                else:
                    logger.warning(f"fifo: unknown command {args[0]}")
                    done_file.write_text("DONE")

                self.do_loop(no_delay=True)

        finally:
            if reader is not None:
                reader.close()

            if fifo_file.exists():
                fifo_file.unlink()

            logger.info("-- Endo Fifo Control --")
