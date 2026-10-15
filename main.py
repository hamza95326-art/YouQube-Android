import asyncio
import os
import re
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import flet as ft

# Optional dependency: install yt-dlp for search, metadata, and downloading.
try:
    import yt_dlp
except ImportError:
    yt_dlp = None


APP_NAME = "YouQube"
BG = "#0F0F0F"
SURFACE = "#202020"
SURFACE_2 = "#272727"
TEXT = "#F1F1F1"
MUTED = "#AAAAAA"
RED = "#FF0033"


def get_app_folder():
    """Use an app-writable directory on Android and desktop."""
    try:
        folder = Path.home() / "Downloads" / "YouQube"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    except Exception:
        folder = Path.cwd() / "YouQubeDownloads"
        folder.mkdir(parents=True, exist_ok=True)
        return folder


def get_database_path():
    folder = Path.home() / ".youqube"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "videos.db"
    except Exception:
        return Path.cwd() / "videos.db"


DB_PATH = get_database_path()
DOWNLOAD_DIR = get_app_folder()


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            file_path TEXT DEFAULT '',
            thumbnail TEXT DEFAULT '',
            status TEXT DEFAULT 'completed'
        )
    """)
    conn.commit()
    return conn


def save_video(video_id, title, url, file_path="", thumbnail="", status="completed"):
    with db_connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO videos
               (id, title, url, file_path, thumbnail, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (video_id, title, url, file_path, thumbnail, status),
        )


def get_saved_videos():
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, title, url, file_path, thumbnail, status "
            "FROM videos ORDER BY rowid DESC"
        ).fetchall()


def delete_saved_video(video_id):
    with db_connect() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))


def video_id_from_url(url):
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().replace("www.", "")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0]
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
    return ""


def main(page: ft.Page):
    page.title = APP_NAME
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.spacing = 0
    page.window_min_width = 360
    page.window_min_height = 600

    current_tab = "home"
    active_downloads = set()

    def toast(message):
        page.snack_bar = ft.SnackBar(content=ft.Text(message))
        page.snack_bar.open = True
        page.update()

    def run_in_thread(fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def open_url(url):
        # Flet's launch_url opens the link in the device browser.
        page.launch_url(url)

    search_input = ft.TextField(
        hint_text="ابحث عن فيديوهات YouTube",
        expand=True,
        border_radius=24,
        filled=True,
        fill_color=SURFACE,
        border_color=SURFACE,
        focused_border_color=RED,
        text_size=14,
        content_padding=ft.Padding(16, 10, 16, 10),
        on_submit=lambda e: do_search(),
    )

    url_input = ft.TextField(
        hint_text="الصق رابط فيديو YouTube هنا",
        expand=True,
        border_radius=12,
        filled=True,
        fill_color=SURFACE,
        border_color=SURFACE,
        focused_border_color=RED,
        text_size=14,
        content_padding=ft.Padding(14, 12, 14, 12),
    )

    results_list = ft.Column(spacing=14)
    completed_list = ft.Column(spacing=12)
    page_body = ft.Column(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)

    def header():
        return ft.Container(
            padding=ft.Padding(16, 12, 16, 8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Icon(ft.Icons.SMART_DISPLAY, color=RED, size=32),
                            ft.Text(APP_NAME, size=22, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SETTINGS_OUTLINED,
                        tooltip="الإعدادات",
                        on_click=lambda e: show_tab("settings"),
                    ),
                ],
            ),
        )

    def section_title(text):
        return ft.Text(text, size=18, weight=ft.FontWeight.BOLD)

    def make_video_card(item, show_download=True):
        title = item.get("title") or "بدون عنوان"
        url = item.get("webpage_url") or item.get("url") or ""
        vid = item.get("id") or video_id_from_url(url)
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        thumbnail = item.get("thumbnail") or (
            f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""
        )
        channel = item.get("uploader") or item.get("channel") or "قناة YouTube"
        duration = item.get("duration")
        duration_text = ""
        if duration:
            duration = int(duration)
            duration_text = f"{duration // 60}:{duration % 60:02d}"
        views = item.get("view_count")
        views_text = f"{views:,} مشاهدة" if isinstance(views, int) and views else ""

        image_control = (
            ft.Image(
                src=thumbnail,
                width=145,
                height=100,
                fit=ft.BoxFit.COVER,
                border_radius=10,
                error_content=ft.Container(
                    width=145, height=100, bgcolor=SURFACE_2,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED, color=MUTED),
                ),
            )
            if thumbnail else
            ft.Container(
                width=145, height=100, bgcolor=SURFACE_2, border_radius=10,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(ft.Icons.SMART_DISPLAY, color=RED, size=34),
            )
        )

        buttons = [
            ft.TextButton(
                "فتح",
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=lambda e, u=url: open_url(u) if u else toast("لا يوجد رابط للفيديو"),
            )
        ]
        if show_download:
            buttons.append(
                ft.TextButton(
                    "تنزيل",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e, u=url, t=title, i=vid, th=thumbnail: download_video(
                        i, t, u, th, audio_only=False
                    ),
                )
            )

        return ft.Container(
            padding=10,
            bgcolor=SURFACE,
            border_radius=14,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.GestureDetector(
                        content=image_control,
                        on_tap=lambda e, u=url: open_url(u) if u else None,
                    ),
                    ft.Column(
                        spacing=5,
                        expand=True,
                        controls=[
                            ft.Text(
                                title, size=14, weight=ft.FontWeight.BOLD,
                                max_lines=3, overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(channel, size=12, color=MUTED, max_lines=1),
                            ft.Text(" • ".join(x for x in [views_text, duration_text] if x),
                                    size=11, color=MUTED),
                            ft.Row(controls=buttons, spacing=0, wrap=True),
                        ],
                    ),
                ],
            ),
        )

    def do_search():
        query = (search_input.value or "").strip()
        if not query:
            toast("اكتب كلمة للبحث أولاً")
            return
        if yt_dlp is None:
            toast("ثبّت yt-dlp أولاً. راجع التعليمات أسفل الكود.")
            return

        results_list.controls = [
            ft.Row([ft.ProgressRing(), ft.Text("جارٍ البحث عن الفيديوهات...")])
        ]
        page.update()

        def worker():
            try:
                opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    data = ydl.extract_info(f"ytsearch20:{query}", download=False)
                entries = data.get("entries") or []
                cards = []
                for entry in entries:
                    if not entry:
                        continue
                    entry = dict(entry)
                    if not entry.get("webpage_url") and entry.get("id"):
                        entry["webpage_url"] = f"https://www.youtube.com/watch?v={entry['id']}"
                    cards.append(make_video_card(entry))
                results_list.controls = cards or [ft.Text("لم يتم العثور على نتائج.", color=MUTED)]
            except Exception as ex:
                results_list.controls = [
                    ft.Text(f"تعذّر البحث: {ex}", color="#FF7777", selectable=True)
                ]
            page.update()

        run_in_thread(worker)

    def import_url():
        url = (url_input.value or "").strip()
        vid = video_id_from_url(url)
        if not vid:
            toast("أدخل رابط YouTube صحيحاً")
            return
        if yt_dlp is None:
            # Still allow the user to open a valid YouTube URL without metadata support.
            make_imported_preview(
                {"id": vid, "title": "فيديو YouTube", "webpage_url": url,
                 "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}
            )
            toast("تمت إضافة معاينة. ثبّت yt-dlp لجلب العنوان الحقيقي.")
            return

        imported_area.controls = [ft.Row([ft.ProgressRing(), ft.Text("جارٍ جلب معلومات الفيديو...")])]
        page.update()

        def worker():
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                make_imported_preview(info)
            except Exception as ex:
                imported_area.controls = [ft.Text(f"تعذّر جلب المعلومات: {ex}", color="#FF7777", selectable=True)]
            page.update()

        run_in_thread(worker)

    imported_area = ft.Column(spacing=10)

    def make_imported_preview(info):
        vid = info.get("id") or video_id_from_url(info.get("webpage_url", ""))
        title = info.get("title") or "فيديو YouTube"
        url = info.get("webpage_url") or url_input.value or ""
        thumbnail = info.get("thumbnail") or (
            f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""
        )
        item = {
            "id": vid, "title": title, "webpage_url": url,
            "thumbnail": thumbnail, "uploader": info.get("uploader", ""),
            "duration": info.get("duration"),
        }
        imported_area.controls = [
            section_title("الفيديو المحدد"),
            make_video_card(item, show_download=False),
            ft.Row(
                wrap=True,
                controls=[
                    ft.OutlinedButton(
                        "فتح على YouTube", icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda e, u=url: open_url(u),
                    ),
                    ft.FilledButton(
                        "تنزيل MP4", icon=ft.Icons.DOWNLOAD,
                        on_click=lambda e: download_video(vid, title, url, thumbnail, False),
                    ),
                    ft.OutlinedButton(
                        "تنزيل صوت", icon=ft.Icons.MUSIC_NOTE,
                        on_click=lambda e: download_video(vid, title, url, thumbnail, True),
                    ),
                ],
            ),
        ]
        page.update()

    def download_video(vid, title, url, thumbnail="", audio_only=False):
        if not url:
            toast("رابط الفيديو غير متاح")
            return
        if yt_dlp is None:
            toast("ميزة التنزيل تحتاج مكتبة yt-dlp")
            return
        key = str(vid or url)
        if key in active_downloads:
            toast("هذا الفيديو قيد التنزيل بالفعل")
            return
        active_downloads.add(key)
        save_video(key, title, url, "", thumbnail, "downloading")
        toast("بدأ التنزيل. قد يفشل على Android لبعض الفيديوهات أو الصيغ.")

        def worker():
            try:
                opts = {
                    "outtmpl": str(DOWNLOAD_DIR / "%(title).100s [%(id)s].%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "restrictfilenames": True,
                }
                if audio_only:
                    # Extracts the best audio stream; converting it to MP3 needs FFmpeg.
                    opts["format"] = "bestaudio[ext=m4a]/bestaudio"
                else:
                    # Prefer a single-file MP4 stream so merging with FFmpeg is not required.
                    opts["format"] = "best[ext=mp4][protocol^=https]/best[ext=mp4]/best"
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                if not Path(filename).exists():
                    # yt-dlp may change the final extension.
                    candidates = list(DOWNLOAD_DIR.glob(f"*{vid}*"))
                    filename = str(candidates[-1]) if candidates else filename
                save_video(key, title, url, filename, thumbnail, "completed")
                toast(f"اكتمل التنزيل: {Path(filename).name}")
            except Exception as ex:
                save_video(key, title, url, "", thumbnail, "failed")
                toast(f"فشل التنزيل: {ex}")
            finally:
                active_downloads.discard(key)
                refresh_completed()
                page.update()

        run_in_thread(worker)

    def refresh_completed():
        rows = get_saved_videos()
        completed_list.controls = []
        for vid, title, url, path, thumb, status in rows:
            file_exists = bool(path and Path(path).exists())
            action_controls = [
                ft.TextButton(
                    "فتح الرابط", icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda e, u=url: open_url(u),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="حذف من القائمة",
                    on_click=lambda e, i=vid: remove_saved(i),
                ),
            ]
            if file_exists:
                action_controls.insert(
                    0,
                    ft.TextButton(
                        "موقع الملف", icon=ft.Icons.FOLDER_OPEN,
                        on_click=lambda e, p=path: toast(f"حُفظ الملف في: {p}"),
                    ),
                )
            completed_list.controls.append(
                ft.Container(
                    bgcolor=SURFACE, border_radius=12, padding=12,
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Text(title, weight=ft.FontWeight.BOLD, max_lines=2),
                            ft.Text(
                                {"completed": "مكتمل", "downloading": "قيد التنزيل", "failed": "فشل التنزيل"}.get(status, status),
                                color={"completed": "#5BD68B", "downloading": "#F4C95D", "failed": "#FF7777"}.get(status, MUTED),
                                size=12,
                            ),
                            ft.Text(path if file_exists else "لا يوجد ملف محفوظ لهذا العنصر", size=11, color=MUTED, selectable=True),
                            ft.Row(action_controls, wrap=True, spacing=0),
                        ],
                    ),
                )
            )
        if not rows:
            completed_list.controls = [ft.Text("لا توجد تنزيلات محفوظة بعد.", color=MUTED)]
        page.update()

    def remove_saved(vid):
        delete_saved_video(vid)
        refresh_completed()
        toast("تم حذف العنصر من القائمة")

    def home_view():
        return [
            header(),
            ft.Container(
                padding=ft.Padding(12, 0, 12, 10),
                content=ft.Row(
                    controls=[
                        search_input,
                        ft.IconButton(
                            icon=ft.Icons.SEARCH, icon_color=TEXT,
                            bgcolor=RED, on_click=lambda e: do_search(),
                            tooltip="بحث",
                        ),
                    ],
                ),
            ),
            ft.Container(
                padding=ft.Padding(16, 4, 16, 8),
                content=ft.Column(
                    spacing=12,
                    controls=[
                        section_title("البحث عن فيديو"),
                        ft.Text("ابحث عن فيديوهات أو افتح رابطاً مباشراً.", color=MUTED, size=12),
                        ft.Row(
                            controls=[
                                url_input,
                                ft.IconButton(
                                    icon=ft.Icons.ADD_LINK, icon_color=TEXT,
                                    bgcolor=SURFACE_2, on_click=lambda e: import_url(),
                                    tooltip="استيراد رابط",
                                ),
                            ],
                        ),
                        imported_area,
                        ft.Divider(color="#333333"),
                        section_title("نتائج البحث"),
                        results_list,
                    ],
                ),
            ),
        ]

    def downloads_view():
        refresh_completed()
        return [
            header(),
            ft.Container(
                padding=16,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        section_title("التنزيلات"),
                        ft.Text(f"مجلد التنزيل داخل التطبيق: {DOWNLOAD_DIR}", color=MUTED, size=12, selectable=True),
                        completed_list,
                    ],
                ),
            ),
        ]

    def settings_view():
        return [
            header(),
            ft.Container(
                padding=18,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        section_title("الإعدادات"),
                        ft.Text("المظهر", weight=ft.FontWeight.BOLD),
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    "داكن",
                                    on_click=lambda e: set_theme(ft.ThemeMode.DARK),
                                ),
                                ft.OutlinedButton(
                                    "فاتح",
                                    on_click=lambda e: set_theme(ft.ThemeMode.LIGHT),
                                ),
                            ],
                        ),
                        ft.Text("مكان حفظ الملفات", weight=ft.FontWeight.BOLD),
                        ft.Text(str(DOWNLOAD_DIR), color=MUTED, selectable=True),
                        ft.Text(
                            "ملاحظات Android:\n"
                            "• الملفات تُحفظ في مجلد التطبيق القابل للكتابة.\n"
                            "• تنزيل الصوت بصيغة MP3 يحتاج FFmpeg للتحويل؛ هذه النسخة تحفظ أفضل مسار صوت متاح مثل M4A.\n"
                            "• دعم yt-dlp على YouTube يتغير باستمرار، وقد لا تعمل بعض الفيديوهات أو الصيغ على الهاتف.",
                            color=MUTED, size=12,
                        ),
                    ],
                ),
            ),
        ]

    def set_theme(mode):
        page.theme_mode = mode
        page.update()

    def show_tab(tab):
        nonlocal current_tab
        current_tab = tab
        page_body.controls.clear()
        if tab == "home":
            page_body.controls = home_view()
        elif tab == "downloads":
            page_body.controls = downloads_view()
        elif tab == "settings":
            page_body.controls = settings_view()
        elif tab == "shorts":
            page_body.controls = [
                header(),
                ft.Container(padding=20, content=ft.Text("افتح Shorts من تطبيق YouTube الرسمي.", color=MUTED)),
                ft.Container(padding=20, content=ft.FilledButton(
                    "فتح YouTube", icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda e: open_url("https://m.youtube.com/shorts"),
                )),
            ]
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor="#181818",
        indicator_color="#3A2525",
        on_change=lambda e: show_tab(["home", "downloads", "shorts", "settings"][e.control.selected_index]),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="الرئيسية"),
            ft.NavigationBarDestination(icon=ft.Icons.DOWNLOAD_OUTLINED, selected_icon=ft.Icons.DOWNLOAD, label="التنزيلات"),
            ft.NavigationBarDestination(icon=ft.Icons.PLAY_CIRCLE_OUTLINE, selected_icon=ft.Icons.PLAY_CIRCLE, label="Shorts"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="الإعدادات"),
        ],
    )

    page.add(
        ft.SafeArea(
            content=page_body,
            expand=True,
        )
    )
    show_tab("home")


if __name__ == "__main__":
    ft.run(main)
