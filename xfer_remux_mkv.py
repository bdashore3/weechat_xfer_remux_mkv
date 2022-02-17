import re
from subprocess import call, DEVNULL
from pathlib import Path
from shutil import which

# For checking WeeChat import
import_ok = True

try:
    import weechat
except ImportError:
    print("You must run this script within WeeChat!\n"
          "http://weechat.org")
    import_ok = False

SCRIPT_NAME = "xfer_remux_mkv"
SCRIPT_AUTHOR = "Brian Dashore <bdashore3@gmail.com>, Riven Skaye <riven@tae.moe>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC = "Remuxes mkv files to mp4 on an xfer end event"

"""Configuration options are stored here

To set options, type /set plugins.var.python.xfer_remux_mkv.<option_name> <option_value>
You can view and interactively set options by using /fset plugins.var.python.xfer_remux_mkv.*
"""
OPTIONS = {
    "ffmpeg": ("", "Exact path to your copy of ffmpeg. Not required if ffmpeg lives on your PATH"),
    "pattern": ("", "Override the replacement pattern"),
    "keep": ("false", "Keep the original mkv file"),
    "overwrite": ("true", "Overwrite the file outputted by ffmpeg"),
    "debug": ("false", "Prints out source and destination paths")
}

# These symbols are absolutely unwanted for filenames.
danger = re.compile(r"[\~\$\{\}\!\?\|\:\s]")
# These symbols represent info that is already in the metadata.
groupnames = re.compile(r"\_*\[\S+?\]\_*")

def xfer_ended_signal_cb(data, signal, signal_data):
    """Defer to this function once an xfer completes"""
    try:
        ffmpeg = get_ffmpeg()
    except EnvironmentError as e:
        print(e)
        return 1

    weechat.infolist_next(signal_data)

    filename = weechat.infolist_string(signal_data, "filename")

    local_filename = weechat.infolist_string(signal_data, "local_filename")
    local_filepath = Path(local_filename)

    try:
        outfile = fetch_outfile(local_filepath)
    except ValueError as e:
        print(f"Outfile fetch error!: {e} \n")
        return 1

    # If we want to debug file paths, print the paths and exit
    if weechat_config_get_boolean("debug"):
        print(f"Infile path: `{local_filename}` \n"
              f"Outfile path: `{outfile}` \n")
        return 0

    try:
        result = do_ffmpeg(str(ffmpeg), local_filename, outfile)
    except NameError as e:
        print(f"ffmpeg function error!: {e} \n")
        return 1

    print(f'Your file {filename} has been converted to mp4 and stored in {outfile}')

    if not weechat_config_get_boolean("keep"):
        local_filepath.unlink()
        print("Due to your preferences, the original mkv has been removed \n")

    return result

def get_outname(name: str) -> str:
    """Removes unwanted components from a filename and returns a proper output name.

    This function removes dangerous components from filenames to prevent
    silly crafted names like 'somefile ; rm -rf "$SHELL"' from breaking the system.
    If the name collides, ffmpeg will not output anything by default, unless the -y flag
    is specified.
    """
    chunks = name.split(".")[1:]
    spliced_name = "".join(chunks[:-1]) + ".mp4"

    replacements = weechat.config_get_plugin("pattern")
    if replacements:
        replacements = re.compile(replacements)
    else:
        replacements = danger

    safe = re.sub(replacements, "", spliced_name)
    return re.sub(groupnames, "", safe).replace("_-_", "-")

def fetch_outfile(infile: Path) -> Path:
    """Creates the output path based on the input path.

    This is used to make sure `../processed/` exists and to generate the full
    path for ffmpeg to output the remuxed file to.
    """
    if not infile.is_file():
        raise ValueError(f"{infile} is not a file or symlink!")
    
    if not infile.name.endswith(".mkv"):
        raise ValueError(f"{infile.name} is not a matroska video file!")

    # Make sure we have the correct, absolute directory for ffmpeg
    indir = infile.parent.absolute().resolve()

    outdir = indir.parent.joinpath("processed")
    # Create outdir if it doesn't exist
    outdir.mkdir(exist_ok=True)

    outfile = get_outname(infile.name)
    return outdir.joinpath(outfile)


def do_ffmpeg(ffmpeg: str, infile: str, outfile: str) -> int:
    """Executor function for ffmpeg. Returns the exit status to be used later.

    If the exit status is non-zero (indicating something went wrong), the user
    should handle the issue themselves. There are very few things that could
    cause this ffmpeg command to go wrong, according to the authors of this script.
    """
    ffmpeg_args = [
        ffmpeg,
        "-i", infile,
        "-c", "copy",
        # Allow experimental codec support like Opus and FLAC
        "-strict", "-2",
        # If present, allow subs to be transformed too
        "-c:s", "mov_text", outfile
    ]

    if weechat_config_get_boolean("overwrite"):
      ffmpeg_args += ["-y"]

    return call(ffmpeg_args, stdout=DEVNULL, stderr=DEVNULL)

def weechat_config_get_boolean(config_key: str) -> int:
    """Use weechat's methods to convert truthy values to boolean ones.

    In this case, the method returns an integer, so return an integer.
    Anything other than a value that resembles true is returned as 0.
    """
    config_value = weechat.config_get_plugin(config_key)
    return weechat.config_string_to_boolean(config_value)

def init_config():
    """Initialized the plugin configuration"""
    for option, value in OPTIONS.items():
        weechat.config_set_desc_plugin(option, f"{value[1]} (default: '{value[0]}')")
        if not weechat.config_is_set_plugin(option):
            weechat.config_set_plugin(option, value[0])

def get_ffmpeg():
    """Check for a ffmpeg path and return a custom one if the user set it"""
    custom_ffmpeg_path = weechat.config_get_plugin("ffmpeg")

    ffmpeg = custom_ffmpeg_path if len(custom_ffmpeg_path) > 0 else which("ffmpeg")
    if ffmpeg is None:
        raise EnvironmentError("Error: ffmpeg could not be found on the system! Please install ffmpeg or unload this plugin!")

    return ffmpeg

if __name__ == "__main__" and import_ok:
    """Main call. Only executes if the weechat module is imported"""
    registered = weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                                  SCRIPT_LICENSE, SCRIPT_DESC, "", "")
    if registered:
        init_config()
        weechat.hook_signal("xfer_ended", "xfer_ended_signal_cb", "")
