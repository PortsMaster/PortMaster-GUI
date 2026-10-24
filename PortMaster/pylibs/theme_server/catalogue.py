# SPDX-License-Identifier: MIT
#
# The screens the theme server renders, in the page's order: (name, title). shots.py has
# a builder for each, shot_<name>. Kept apart, so serve.py lists them without starting
# a renderer.

SHOTS = (
    ("main_menu", "Main menu"),
    ("ports_all", "All ports"),
    ("ports_rtr", "Ready to run ports"),
    ("ports_manage", "Manage ports"),
    ("port_info", "Port info"),
    ("port_info_popup", "Port info popup"),
    ("port_links", "Port links (store and website QR codes)"),
    ("filters", "Filters"),
    ("featured", "Featured ports"),
    ("featured_list", "Featured ports list"),
    ("options", "Options"),
    ("runtimes", "Runtimes"),
    ("themes", "Themes"),
    ("theme_schemes", "Colour schemes"),
    ("language", "Language"),
    ("keyboard", "On-screen keyboard"),
    ("theme_editor", "Theme editor (its address and QR code)"),
    ("messages", "Messages and progress"),
    ("message_box", "Message box"),
    ("selection_list", "Selection list"),
    ("selection_description", "Selection list + description"),
    ("selection_images", "Selection list + images"),
    ("selection_description_images", "Selection list + description + images"),
    ("disclaimer", "Disclaimer"),
    ("warning_trimui", "Unsupported system warning (TrimUI)"),
    ("warning_long", "Unsupported system warning (spruce, low RAM)"),
    )
