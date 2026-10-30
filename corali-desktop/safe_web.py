"""Public-only yt-dlp transport: validate and connect to the same DNS result.

No process-wide socket patches. Redirects and fragment/key requests all use this
transport. External network downloaders and live streams fail closed.
"""

import http.client
import ipaddress
import socket
import urllib.parse
import urllib.request

from yt_dlp import YoutubeDL
from yt_dlp.networking._urllib import HTTPHandler, RedirectHandler, UrllibRH
from yt_dlp.downloader.hls import HlsFD
from yt_dlp.dependencies import Cryptodome


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or "%" in parsed.hostname
    ):
        raise ValueError(
            "Inserisci un collegamento pubblico HTTP o HTTPS senza credenziali."
        )
    parsed.port  # Reject invalid ports before any request.
    return parsed


def public_connection(
    address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None
):
    host, port = address
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise OSError("Indirizzo del sito non disponibile.")
    for _, _, _, _, target in addresses:
        ip = ipaddress.ip_address(target[0])
        if not ip.is_global or ip.is_multicast or ip.is_unspecified:
            raise ValueError(
                "Collegamento bloccato: il sito punta a un indirizzo locale o riservato."
            )
    last = None
    for family, kind, protocol, _, target in addresses:
        sock = socket.socket(family, kind, protocol)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(target)  # Numeric address: no second DNS lookup.
            return sock
        except OSError as error:
            last = error
            sock.close()
    raise last or OSError("Connessione al sito non riuscita.")


class PublicHTTPHandler(HTTPHandler):
    def _open(self, req, cls, **kwargs):
        validate_url(req.full_url)
        if req.has_proxy() or req.has_header("Ytdl-socks-proxy"):
            raise ValueError("Proxy non consentito per i download web protetti.")

        def connection(*args, **options):
            conn = cls(*args, **options)
            conn._create_connection = public_connection
            return conn

        return self.do_open(connection, req, **kwargs)

    def http_open(self, req):
        return self._open(req, http.client.HTTPConnection)

    def https_open(self, req):
        return self._open(req, http.client.HTTPSConnection, context=self._context)


class PublicRedirectHandler(RedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicRH(UrllibRH):
    _SUPPORTED_URL_SCHEMES = ("http", "https")

    def _create_instance(self, proxies, cookiejar, legacy_ssl_support=None):
        opener = urllib.request.OpenerDirector()
        for handler in (
            PublicHTTPHandler(
                context=self._make_sslcontext(legacy_ssl_support=legacy_ssl_support)
            ),
            urllib.request.HTTPCookieProcessor(cookiejar),
            urllib.request.UnknownHandler(),
            urllib.request.HTTPDefaultErrorHandler(),
            urllib.request.HTTPErrorProcessor(),
            PublicRedirectHandler(),
        ):
            opener.add_handler(handler)
        opener.addheaders = []
        return opener


class PublicYoutubeDL(YoutubeDL):
    def build_request_director(self, handlers, preferences=None):
        return super().build_request_director([PublicRH], [])

    def run_pp(self, pp, infodict):
        from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor

        if isinstance(pp, FFmpegPostProcessor) and not getattr(
            pp, "_corali_local_only", False
        ):
            original = pp.get_metadata_object
            pp.get_metadata_object = lambda path, opts=(): original(
                path, [*opts, "-protocol_whitelist", "file,pipe"]
            )

            def audio_codec(path):
                if pp.probe_available:
                    return next(
                        (
                            s.get("codec_name")
                            for s in pp.get_metadata_object(path)["streams"]
                            if s.get("codec_type") == "audio"
                        ),
                        None,
                    )
                import os, re, subprocess

                result = subprocess.run(
                    [
                        pp.executable,
                        "-protocol_whitelist",
                        "file,pipe",
                        "-i",
                        pp._ffmpeg_filename_argument(path),
                    ],
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    timeout=60,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                match = re.search(
                    r"Audio:\s*([0-9a-z]+)",
                    result.stderr.decode("utf8", errors="replace"),
                )
                return match[1] if match else None

            pp.get_audio_codec = audio_codec
            pp._corali_local_only = True
        return super().run_pp(pp, infodict)

    def dl(self, name, info, subtitle=False, test=False):
        # FFmpeg is only allowed to process downloaded local files, never URLs.
        for item in info.get("requested_formats") or [info]:
            protocol = (
                item.get("protocol")
                or urllib.parse.urlsplit(item.get("url", "")).scheme
            )
            if item.get("is_live") or protocol not in (
                "http",
                "https",
                "http_dash_segments",
                "m3u8_native",
                "m3u8",
            ):
                raise ValueError(
                    "Questo flusso richiede un download esterno non protetto. Usa un file audio o video locale."
                )
            validate_url(item["url"])
            if protocol in ("m3u8", "m3u8_native"):
                manifest = item.get("hls_media_playlist_data")
                if not manifest:
                    from yt_dlp.networking import Request

                    with self.urlopen(
                        Request(item["url"], headers=item.get("http_headers", {}))
                    ) as response:
                        item["url"] = response.url
                        raw = response.read(8 * 1024 * 1024 + 1)
                    if len(raw) > 8 * 1024 * 1024:
                        raise ValueError("Playlist troppo grande.")
                    manifest = raw.decode("utf-8", "replace")
                if not HlsFD.can_download(manifest, item) or (
                    "#EXT-X-KEY:METHOD=AES-128" in manifest and not Cryptodome.AES
                ):
                    raise ValueError(
                        "Playlist non supportata dal download protetto. Usa un file locale."
                    )
                item["hls_media_playlist_data"] = manifest
                item["protocol"] = "m3u8_native"
        return super().dl(name, info, subtitle=subtitle, test=test)
