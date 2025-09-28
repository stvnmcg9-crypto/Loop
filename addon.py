import sys
import xbmcplugin
import xbmcgui
import xbmcaddon
from urllib.parse import parse_qs, urlparse, urlencode
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])

# --- CONFIGURATION ---
# Replace these URLs with your own M3U and EPG sources!
M3U_URL = "https://iptv-org.github.io/iptv/countries/us.m3u"
EPG_URL = "https://iptv-org.github.io/epg/guides/us.xml"
TIME_FORMAT = "%Y%m%d%H%M%S %z"

# --- AUTHENTICATION/REGION STUBS ---
def is_authenticated():
    # Placeholder: implement your authentication here
    # Return True if authenticated, else False
    return True

def is_region_allowed():
    # Placeholder: implement your region restriction here
    # Return True if region allowed, else False
    return True

def build_url(query):
    return sys.argv[0] + '?' + urlencode(query)

def parse_m3u(url):
    response = requests.get(url)
    response.raise_for_status()
    content = response.text
    channels = []
    regex = re.compile(
        r'#EXTINF:-1.*?tvg-id="(.*?)".*?tvg-name="(.*?)".*?group-title="(.*?)".*?,(.*?)\n(https?://.*?)\n',
        re.DOTALL)
    for match in regex.finditer(content):
        tvg_id, tvg_name, group, name, stream_url = match.groups()
        channels.append({
            "tvg_id": tvg_id,
            "name": name,
            "stream_url": stream_url
        })
    return channels

def parse_epg(url):
    response = requests.get(url)
    response.raise_for_status()
    epg = {}
    tree = ET.fromstring(response.content)
    for prog in tree.findall('./programme'):
        channel = prog.attrib['channel']
        start = prog.attrib['start']
        stop = prog.attrib['stop']
        title_el = prog.find('title')
        title = title_el.text if title_el is not None else "Unknown"
        desc_el = prog.find('desc')
        desc = desc_el.text if desc_el is not None else ""
        if channel not in epg:
            epg[channel] = []
        epg[channel].append({
            "start": start,
            "stop": stop,
            "title": title,
            "desc": desc
        })
    return epg

def get_today_epg(epg, channel_id):
    progs = epg.get(channel_id, [])
    today = datetime.utcnow().date()
    today_progs = []
    for prog in progs:
        # EPG times are like: 20230928160000 +0000
        try:
            start_dt = datetime.strptime(prog["start"], "%Y%m%d%H%M%S %z")
        except Exception:
            continue
        if start_dt.date() == today:
            today_progs.append({
                "title": prog["title"],
                "desc": prog["desc"],
                "start": start_dt,
                "stop": datetime.strptime(prog["stop"], "%Y%m%d%H%M%S %z") if prog["stop"] else None
            })
    return today_progs

def list_channels():
    if not is_authenticated():
        xbmcgui.Dialog().notification("Loop Clone", "Authentication required.", xbmcgui.NOTIFICATION_ERROR, 2000)
        return
    if not is_region_allowed():
        xbmcgui.Dialog().notification("Loop Clone", "Region not allowed.", xbmcgui.NOTIFICATION_ERROR, 2000)
        return

    xbmcgui.Dialog().notification("Loop Clone", "Fetching channels...", xbmcgui.NOTIFICATION_INFO, 1500)
    try:
        channels = parse_m3u(M3U_URL)
        epg = parse_epg(EPG_URL)
    except Exception as e:
        xbmcgui.Dialog().notification("Loop Clone", f"Error: {e}", xbmcgui.NOTIFICATION_ERROR, 3000)
        return
    for channel in channels:
        label = channel["name"]
        # Find the current program
        now = datetime.utcnow()
        today_epg = get_today_epg(epg, channel["tvg_id"])
        current_prog = None
        for prog in today_epg:
            if prog["start"] <= now <= (prog["stop"] or now):
                current_prog = prog
                break
        if current_prog:
            label += f" [COLOR gold]({current_prog['title']})[/COLOR]"
            info = {"plot": current_prog.get("desc", "")}
        else:
            info = {}
        li = xbmcgui.ListItem(label=label)
        li.setInfo("video", info)
        # Directory, not playable: clicking will show EPG
        url = build_url({"epg": channel["tvg_id"], "name": channel["name"], "stream_url": channel["stream_url"]})
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_epg_for_channel(tvg_id, channel_name, stream_url):
    xbmcgui.Dialog().notification("Loop Clone", f"Loading EPG for {channel_name}", xbmcgui.NOTIFICATION_INFO, 1000)
    try:
        epg = parse_epg(EPG_URL)
    except Exception as e:
        xbmcgui.Dialog().notification("EPG error", str(e), xbmcgui.NOTIFICATION_ERROR, 3000)
        return
    today_epg = get_today_epg(epg, tvg_id)
    if not today_epg:
        xbmcgui.Dialog().ok("EPG", f"No EPG found for {channel_name} today.")
        return
    for prog in today_epg:
        start_str = prog["start"].strftime("%H:%M")
        stop_str = prog["stop"].strftime("%H:%M") if prog["stop"] else ""
        label = f"{start_str}-{stop_str} {prog['title']}"
        li = xbmcgui.ListItem(label=label)
        li.setInfo("video", {"plot": prog["desc"]})
        li.setProperty("IsPlayable", "true")
        url = build_url({"play": stream_url})
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)
    xbmcplugin.endOfDirectory(HANDLE)

def play_stream(url):
    li = xbmcgui.ListItem(path=url)
    xbmcplugin.setResolvedUrl(HANDLE, True, listitem=li)

if __name__ == "__main__":
    args = parse_qs(urlparse(sys.argv[2]).query)
    if "play" in args:
        play_stream(args["play"][0])
    elif "epg" in args and "stream_url" in args and "name" in args:
        list_epg_for_channel(args["epg"][0], args["name"][0], args["stream_url"][0])
    else:
        list_channels()