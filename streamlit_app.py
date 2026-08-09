import glob
import os
import re
import subprocess
import tempfile

import streamlit as st
import yt_dlp


st.set_page_config(
    page_title="YouTube Video Downloader",
    page_icon="🎬",
    layout="centered",
)


def sanitize_filename(title: str) -> str:
    """Create a filesystem-safe filename from a media title."""
    safe_title = "".join(
        c if c.isalnum() or c in " -_()" else "_"
        for c in title
    ).strip()

    # Keep the behavior of the original notebook while avoiding empty names.
    safe_title = safe_title[:80] or "video"
    return safe_title


class StreamlitLogger:
    """Collect yt-dlp log messages for optional display in Streamlit."""

    def __init__(self):
        self.messages = []

    def debug(self, msg):
        self.messages.append(str(msg))

    def warning(self, msg):
        self.messages.append(f"WARNING: {msg}")

    def error(self, msg):
        self.messages.append(f"ERROR: {msg}")


def get_title(url: str) -> str:
    """Fetch the video's title without downloading the media."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("title", "video")


def download_media(url: str, mode: str, progress_bar, status_text):
    """
    Download and process the requested media.

    Returns:
        tuple[bytes, str, str]: file data, download filename, MIME type
    """
    logger = StreamlitLogger()

    def progress_hook(data):
        status = data.get("status")

        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)

            if total:
                percent = min(100, int(downloaded / total * 100))
                progress_bar.progress(percent)
                status_text.write(f"Downloading… {percent}%")

        elif status == "finished":
            progress_bar.progress(100)
            status_text.write("Download finished. Processing media…")

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            raw_title = get_title(url)
            safe_title = sanitize_filename(raw_title)
            out_name = f"output_{safe_title}"

            if mode == "video":
                ydl_opts = {
                    "format": "best[ext=mp4]/best",
                    "outtmpl": os.path.join(temp_dir, f"{out_name}.%(ext)s"),
                    "progress_hooks": [progress_hook],
                    "keep_video": True,
                    "nopostoverwrites": True,
                    "verbose": True,
                    "quiet": False,
                    "logger": logger,
                }
            else:
                ydl_opts = {
                    "outtmpl": os.path.join(temp_dir, f"{out_name}.%(ext)s"),
                    "progress_hooks": [progress_hook],
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "320",
                        }
                    ],
                    "quiet": False,
                    "logger": logger,
                }

            status_text.write("Downloading…")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if mode == "video":
                # Find the separately downloaded video/audio streams.
                video_file = next(
                    (
                        f
                        for f in glob.glob(
                            os.path.join(temp_dir, f"{out_name}.f*.mp4")
                        )
                    ),
                    None,
                )

                audio_file = (
                    next(
                        (
                            f
                            for f in glob.glob(
                                os.path.join(temp_dir, f"{out_name}.f*.m4a")
                            )
                        ),
                        None,
                    )
                    or next(
                        (
                            f
                            for f in glob.glob(
                                os.path.join(temp_dir, f"{out_name}.f*.webm")
                            )
                        ),
                        None,
                    )
                )

                output_file = os.path.join(temp_dir, f"{out_name}.mp4")

                if video_file and audio_file:
                    status_text.write("Merging and converting…")

                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            video_file,
                            "-i",
                            audio_file,
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "23",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            "-movflags",
                            "+faststart",
                            output_file,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                    # Remove intermediate streams after successful conversion.
                    os.remove(video_file)
                    os.remove(audio_file)

                if not os.path.exists(output_file):
                    raise FileNotFoundError(
                        "The processed MP4 file could not be found."
                    )

                with open(output_file, "rb") as file:
                    file_data = file.read()

                return file_data, f"{safe_title}.mp4", "video/mp4"

            else:
                audio_output = os.path.join(temp_dir, f"{out_name}.mp3")

                if not os.path.exists(audio_output):
                    raise FileNotFoundError(
                        "The processed MP3 file could not be found."
                    )

                with open(audio_output, "rb") as file:
                    file_data = file.read()

                return file_data, f"{safe_title}.mp3", "audio/mpeg"

        except Exception:
            raise

        finally:
            # Keep the logger accessible to the caller if desired.
            pass


st.title("🎬 YouTube Video Downloader")
st.write(
    "Download music videos as high-quality MP4 files or extract "
    "high-quality MP3 audio."
)

st.write(yt_dlp.version.__version__)

url = st.text_input(
    "Video URL",
    placeholder="Paste YouTube URL here",
)

format_choice = st.selectbox(
    "Format",
    options=[
        ("MP4 Video (best quality)", "video"),
        ("MP3 Audio only", "audio"),
    ],
    format_func=lambda option: option[0],
)

show_debug = st.checkbox(
    "Show yt-dlp Output",
    help="Display detailed yt-dlp diagnostic output.",
)

download_clicked = st.button(
    "Download",
    type="primary",
    use_container_width=True,
)

if download_clicked:
    if not url.strip():
        st.error("Please enter a URL.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            with st.spinner("Preparing download…"):
                file_data, filename, mime_type = download_media(
                    url.strip(),
                    format_choice[1],
                    progress_bar,
                    status_text,
                )

            progress_bar.progress(100)
            status_text.success("Download complete!")

            st.download_button(
                label=f"Download {filename}",
                data=file_data,
                file_name=filename,
                mime=mime_type,
                type="primary",
                use_container_width=True,
            )

        except FileNotFoundError as error:
            progress_bar.empty()
            status_text.empty()

            if "ffmpeg" in str(error).lower():
                st.error(
                    "FFmpeg could not be found. Install FFmpeg and make sure "
                    "the `ffmpeg` executable is available on your PATH."
                )
            else:
                st.error(f"Download failed: {error}")

        except subprocess.CalledProcessError as error:
            progress_bar.empty()
            status_text.empty()

            st.error(
                "FFmpeg failed while processing the downloaded media. "
                "Please check that FFmpeg is installed correctly."
            )

            if show_debug and error.stderr:
                with st.expander("FFmpeg Output"):
                    st.code(error.stderr)

        except Exception as error:
            progress_bar.empty()
            status_text.empty()

            st.error("Download failed.")
            if show_debug:
                with st.expander("Error Details", expanded=True):
                    st.exception(error)
            else:
                st.write(str(error))

st.divider()

with st.expander("How to use"):
    st.markdown(
        """
1. Paste the music video URL.
2. Choose **MP4 Video** or **MP3 Audio**.
3. Click **Download**.
4. Wait for the progress bar and media processing.
5. Click the resulting download button.

**Notes**
- Designed primarily for music videos.
- Very long videos may take considerable time or fail because of
  resource/time limits on the machine hosting the app.
- If an error occurs, verify the URL and make sure FFmpeg is installed.
        """
    )

if show_debug:
    st.info(
        "Detailed yt-dlp logging is collected during the download. "
        "For a production deployment, consider enabling this only when "
        "troubleshooting."
    )
