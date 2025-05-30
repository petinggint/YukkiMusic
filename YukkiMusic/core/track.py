import asyncio
import os
import re
from dataclasses import dataclass

from yt_dlp import YoutubeDL

from config import YTDOWNLOADER, cookies
from YukkiMusic.utils.database import is_on_off
from YukkiMusic.utils.decorators import asyncify

from .enum import SourceType

__all__ = ["Track"]


@dataclass
class Track:
    title: str
    link: str
    duration: int  # duration in seconds
    streamtype: SourceType
    video: bool

    thumb: str | None = None
    download_url: str | None = (
        None  # If provided directly used to download instead self.link
    )
    is_live: bool | None = None
    vidid: str | None = (
        None  # TODO: Replace it with track_id  where it will support and mostly used in inline play mode
    )
    file_path: str | None = None

    def __post_init__(self):
        self.download_url = self.download_url if self.download_url else self.link
        if self.is_youtube and self.vidid is None:
            pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
            p_match = re.search(pattern, self.download_url)
            self.vidid = p_match.group(1)
        else:
            self.vidid = ""

        self.title = self.title.title() if self.title is not None else None
        if (
            not self.duration and self.is_live is None
        ):  # WHEN is_live is not None it means the track is live or not live means no need to check it
            if self.streamtype in [
                SourceType.APPLE,
                SourceType.RESSO,
                SourceType.SPOTIFY,
                SourceType.YOUTUBE,
            ]:
                self.is_live = True

    async def __call__(self):
        return self.file_path or await self.download()

    def __getitem__(self, name):
        return getattr(self, name)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    async def is_exists(self):
        exists = False

        if self.file_path:
            if await is_on_off(YTDOWNLOADER):
                exists = os.path.exists(self.file_path)
            else:
                exists = (
                    len(self.file_path) > 30
                )  # FOR m3u8 URLS for m3u8 download mode

        return exists

    @property
    def is_youtube(self) -> bool:
        return "youtube.com" in self.download_url or "youtu.be" in self.download_url

    @property
    def is_m3u8(self) -> bool:
        return self.streamtype == SourceType.M3U8

    async def download(
        self,
    ):
        if (
            self.file_path is not None and await self.is_exists()
        ):  # THIS CONDITION FOR TELEGRAM FILES BECAUSE THESE FILES ARE ALREADY DOWNLOADED
            return self.file_path

        if await is_on_off(YTDOWNLOADER) and not (self.is_live or self.is_m3u8):
            ytdl_opts = {
                "format": (
                    "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])"
                    if self.video
                    else "bestaudio/best"
                ),
                "continuedl": True,
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "quiet": True,
                "retries": 3,
                "no_warnings": True,
            }

            if self.is_youtube:
                ytdl_opts["cookiefile"] = cookies()

            @asyncify
            def _download():
                with YoutubeDL(ytdl_opts) as ydl:
                    info = ydl.extract_info(self.download_url, False)
                    self.file_path = os.path.join(
                        "downloads", f"{info['id']}.{info['ext']}"
                    )

                    if not os.path.exists(self.file_path):
                        ydl.download([self.download_url])

                    return self.file_path

            return await _download()

        else:
            if self.is_m3u8:
                return self.link or self.download_url

            format_code = "b" if self.video else "bestaudio/best"  #
            command = f'yt-dlp -g -f "{format_code}" {"--cookies " + cookies() if self.is_youtube else ""} "{self.download_url}"'
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                self.file_path = stdout.decode("utf-8").strip().split()[0]
                return self.file_path
            else:
                raise Exception(
                    f"Failed to get file path: {stderr.decode('utf-8').strip()}"
                )