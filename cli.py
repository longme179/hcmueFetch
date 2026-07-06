"""Command-line interface."""

import argparse
import sys

from core import (
    DEFAULT_CONFIG,
    DEFAULT_REPORT_DIR,
    DEFAULT_SEEN,
    load_config,
    render_report,
    run_digest,
    save_config,
)


def cmd_run(args):
    sources = load_config(args.config)
    if not sources:
        print(f"Lỗi: Không có nguồn nào trong {args.config}.")
        return 1

    final_items, error_sources = run_digest(
        sources=sources,
        count=args.count,
        mode=args.mode,
        no_excerpt=args.no_excerpt,
        reset_seen=args.all,
        seen_path=args.seen,
    )

    output_path = args.output or f"{DEFAULT_REPORT_DIR}/moi-nhat.txt"
    text = render_report(final_items, args.count, args.mode, error_sources, output_path)
    print(text)
    print(f"Đã lưu báo cáo: {output_path}")
    return 0


def cmd_add(args):
    sources = load_config(args.config)
    if any(s.get("name") == args.name or s.get("url") == args.url for s in sources):
        print("Lỗi: Nguồn hoặc URL đã tồn tại.")
        return 1
    sources.append({"name": args.name, "url": args.url})
    save_config(sources, args.config)
    print(f"Đã thêm nguồn '{args.name}'.")
    return 0


def cmd_remove(args):
    sources = load_config(args.config)
    new_s = [
        s for s in sources if s.get("name") != args.key and s.get("url") != args.key
    ]
    if len(new_s) == len(sources):
        print(f"Không tìm thấy '{args.key}'.")
        return 1
    save_config(new_s, args.config)
    print(f"Đã xoá nguồn '{args.key}'.")
    return 0


def cmd_list(args):
    sources = load_config(args.config)
    if not sources:
        print("(Chưa có nguồn nào)")
        return 0
    for i, s in enumerate(sources, 1):
        print(f"{i}. {s.get('name')} — {s['url']}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="main.py", description="Thu thập tin tức trường, lấy N bài mới nhất."
    )
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Quét và xuất báo cáo.")
    p_run.add_argument(
        "--count", type=int, default=10, help="Số bài mới nhất cần lấy (mặc định 10)."
    )
    p_run.add_argument(
        "--mode",
        choices=["per-source", "combined"],
        default="per-source",
        help="Chế độ lấy bài.",
    )
    p_run.add_argument("--output", help="Đường dẫn file báo cáo.")
    p_run.add_argument("--config", default=DEFAULT_CONFIG, help="File cấu hình nguồn.")
    p_run.add_argument("--seen", default=DEFAULT_SEEN, help="File trạng thái đã-xem.")
    p_run.add_argument(
        "--no-excerpt", action="store_true", help="Không lấy trích đoạn."
    )
    p_run.add_argument(
        "--all", action="store_true", help="Reset đã xem, mọi bài sẽ là [MỚI]."
    )
    p_run.set_defaults(func=cmd_run)

    p_add = sub.add_parser("add", help="Thêm nguồn.")
    p_add.add_argument("name", help="Tên nguồn.")
    p_add.add_argument("url", help="URL nguồn.")
    p_add.add_argument("--config", default=DEFAULT_CONFIG)
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="Xoá nguồn.")
    p_rm.add_argument("key", help="Tên hoặc URL cần xoá.")
    p_rm.add_argument("--config", default=DEFAULT_CONFIG)
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list", help="Liệt kê nguồn.")
    p_ls.add_argument("--config", default=DEFAULT_CONFIG)
    p_ls.set_defaults(func=cmd_list)

    args = parser.parse_args()
    if hasattr(args, "func"):
        sys.exit(args.func(args) or 0)
    else:
        parser.print_help()
