import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
from time import perf_counter_ns, sleep
from tqdm import tqdm
import re
import os
from concurrent.futures import ThreadPoolExecutor
from rich.progress import Progress, SpinnerColumn, DownloadColumn, TimeElapsedColumn, MofNCompleteColumn, TransferSpeedColumn
from rich import pretty
from rich.console import Console
import logging
from rich.logging import RichHandler
from threading import RLock
from rich.console import Group
from rich.live import Live
from typing import Optional
from random import randint
from typing import IO, Any, Callable, List, Optional, TextIO, Type, cast
from types import TracebackType

StdColors = [
    "black","red","green","yellow","blue","magenta","cyan","white","bright_black","bright_red","bright_green","bright_yellow","bright_blue","bright_magenta",
    "bright_cyan","bright_white","grey0","navy_blue","dark_blue","blue3","blue1","dark_green","deep_sky_blue4","dodger_blue3","dodger_blue2","green4",
    "spring_green4","turquoise4","deep_sky_blue3","dodger_blue1","dark_cyan","light_sea_green","deep_sky_blue2","deep_sky_blue1","green3","spring_green3",
    "cyan3","dark_turquoise","turquoise2","green1","spring_green2","spring_green1","medium_spring_green","cyan2","cyan1","purple4","purple3","blue_violet","grey37","medium_purple4","slate_blue3",
    "royal_blue1","chartreuse4","pale_turquoise4","steel_blue","steel_blue3","cornflower_blue","dark_sea_green4","cadet_blue","sky_blue3","chartreuse3",
    "sea_green3","aquamarine3","medium_turquoise","steel_blue1","sea_green2","sea_green1","dark_slate_gray2","dark_red","dark_magenta",
    "orange4","light_pink4","plum4","medium_purple3","slate_blue1","wheat4","grey53","light_slate_grey","medium_purple","light_slate_blue",
    "yellow4","dark_sea_green","light_sky_blue3","sky_blue2","chartreuse2","pale_green3","dark_slate_gray3","sky_blue1","chartreuse1","light_green",
    "aquamarine1","dark_slate_gray1","deep_pink4","medium_violet_red","dark_violet","purple","medium_orchid3","medium_orchid","dark_goldenrod","rosy_brown",
    "grey63","medium_purple2","medium_purple1","dark_khaki","navajo_white3","grey69","light_steel_blue3","light_steel_blue","dark_olive_green3",
    "dark_sea_green3","light_cyan3","light_sky_blue1","green_yellow","dark_olive_green2","pale_green1","dark_sea_green2","pale_turquoise1","red3",
    "deep_pink3","magenta3","dark_orange3","indian_red","hot_pink3","hot_pink2","orchid","orange3","light_salmon3","light_pink3","pink3",
    "plum3","violet","gold3","light_goldenrod3","tan","misty_rose3","thistle3","plum2","yellow3","khaki3","light_yellow3",
    "grey84","light_steel_blue1","yellow2","dark_olive_green1","dark_sea_green1","honeydew2","light_cyan1","red1","deep_pink2","deep_pink1","magenta2",
    "magenta1","orange_red1","indian_red1","hot_pink","medium_orchid1","dark_orange","salmon1","light_coral","pale_violet_red1","orchid2",
    "orchid1","orange1","sandy_brown","light_salmon1","light_pink1","pink1","plum1","gold1","light_goldenrod2",
    "navajo_white1","misty_rose1","thistle1","yellow1","light_goldenrod1","khaki1","wheat1","cornsilk1","grey100","grey3","grey7",
    "grey11","grey15","grey19","grey23","grey27","grey30","grey35","grey39","grey42","grey46",
    "grey50","grey54","grey58","grey62","grey66","grey70","grey74","grey78","grey82","grey85","grey89","grey93"
    ]

class LiveDownload():

    def __init__(self, console=Console()):
        """ 
        Each worker Progress object has the lifecycle:
            1. add_task while assigning the estimated total. Method returns task_id for future reference
            2. advance/update the task as the loop progresses
            3. remove_task when finished

        A Live object manages the Progress object in a Group container.

        All "Live" objects share the same console

        I also found adding a mutex on the console.log helps preventing scrabling output console when multithreading

        """
        self.console = console
        self._lock = RLock()
        self._loglock = RLock()
        self.worker = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            DownloadColumn(binary_units=True),
            TransferSpeedColumn(),
            console=self.console
        )
        self.filesprocessed = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            MofNCompleteColumn(),
            console=self.console
        )
        self.bytestransferred = Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            DownloadColumn(binary_units=True),
            TransferSpeedColumn(),
            console=self.console
        )

        self.group = Group (
            self.filesprocessed,
            self.bytestransferred,
            self.worker,
        )
        self.live = Live(self.group, console=self.console, refresh_per_second=10)

    def log(self, *args, **kwargs):
        with self._loglock:
            self.console.log(*args, **kwargs)

    def start(self, totalfiles, totalbytes):
        self.totalbytes = totalbytes #keep track of total bytes here for `advance_bytestotal``
        self.files = self.filesprocessed.add_task("[blue]FILES", total=totalfiles)
        self.bytes = self.bytestransferred.add_task("[blue]FSIZE", total=totalbytes)
        self.live.__enter__()
        return (self.files, self.bytes)
    
    def finish(self, *args, **kwargs):
        self.filesprocessed.remove_task(self.files)
        self.bytestransferred.remove_task(self.bytes)
        self.live.stop()

    def __enter__(self):
        self.start(1000,1000)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ):
        self.finish()

    def advance_files(self, advance=1):
        with self._lock:
            self.filesprocessed.update(self.files, advance=advance)

    def advance_bytes(self, advance):
        with self._lock:
            self.bytestransferred.update(self.bytes, advance=advance)
    
    def advance_bytestotal(self, advance):
        self.totalbytes += advance
        with self._lock:
            self.bytestransferred.update(self.bytes, total = self.totalbytes)

    def update(self, task_id, *args, **kwargs):
        self.worker.update(task_id=task_id, *args, **kwargs)
    
    def add_task(self, description, *args, **kwargs):
        return self.worker.add_task(description=description, *args, **kwargs)
    
    def remove_task(self, task_id):
        self.worker.remove_task(task_id=task_id)
    
from uuid import uuid4

class Downloader():

    def __init__(self):
        self.console = Console()
        self.live = LiveDownload(console=self.console)
    
    def log(self, *args, **kwargs):
        self.console.log(*args, **kwargs)

    def dummy(self,time):
        ID = str(uuid4())
        
        task_view = self.live.add_task(description=f"{ID}", total = time)
        for _ in range(time):
            sleeptime = randint(1,100)
            self.log(f"[+] {ID} checking in!")
            sleep(sleeptime/100)
            self.live.update(task_id=task_view, advance=1)
        
        self.live.remove_task(task_id=task_view)
        

if __name__=="__main__":
    con = Console()
    d = Downloader()

    #with LiveDownload(console=con) as live:
        #d.dummy(1000)
    time = [randint(1,20) for _ in range(100)]
    d.live.start(1000,1000)
    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.map(d.dummy, time)
    d.live.stop()