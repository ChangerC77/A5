#!/usr/bin/env python3
"""Validate HDF5 dataset quality by checking inter-frame timestamps."""

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np


def _format_interval_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f}ms"


def _format_fps(interval: float) -> str:
    if interval <= 0:
        return "inf"
    return f"{1.0 / interval:.1f}"


def validate_dataset(
    h5_path: str,
    max_frame_interval: float = 0.1,
    min_frame_interval: float = 0.01,
    verbose: bool = False,
) -> dict:
    """Validate HDF5 dataset timestamps.
    
    Args:
        h5_path: Path to HDF5 file
        max_frame_interval: Maximum allowed interval between frames (seconds)
        min_frame_interval: Minimum expected interval between frames (seconds)
        verbose: Print detailed info
    
    Returns:
        Dict with validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "episodes": [],
        "num_episodes": 0,
        "summary": {},
    }

    h5_path = Path(h5_path)
    if not h5_path.exists():
        results["valid"] = False
        results["errors"].append(f"File not found: {h5_path}")
        return results

    with h5py.File(h5_path, "r") as f:
        if "data" not in f:
            results["valid"] = False
            results["errors"].append("No 'data' group in HDF5 file")
            return results

        data_group = f["data"]
        num_demos = len([k for k in data_group.keys() if k.startswith("demo_")])
        
        if num_demos == 0:
            results["valid"] = False
            results["errors"].append("No demo episodes found")
            return results

        results["num_episodes"] = num_demos
        episodes_with_timestamp = 0
        empty_episodes = 0
        single_frame_episodes = 0
        episodes_with_issues = 0
        total_frames = 0
        interval_collections = []
        issue_counts = {
            "large_gaps": 0,
            "small_intervals": 0,
            "duplicates": 0,
            "out_of_order": 0,
        }

        for demo_key in sorted(data_group.keys()):
            if not demo_key.startswith("demo_"):
                continue

            demo_group = data_group[demo_key]
            
            if "timestamp" not in demo_group:
                results["warnings"].append(f"{demo_key}: No timestamp dataset")
                continue

            episodes_with_timestamp += 1
            timestamps = demo_group["timestamp"][:]
            
            if len(timestamps) == 0:
                empty_episodes += 1
                results["warnings"].append(f"{demo_key}: Empty episode")
                continue

            total_frames += len(timestamps)

            episode_result = {
                "name": demo_key,
                "num_frames": len(timestamps),
                "start_time": float(timestamps[0]),
                "end_time": float(timestamps[-1]),
                "duration": float(timestamps[-1] - timestamps[0]),
                "frame_intervals": [],
                "issues": [],
            }

            if len(timestamps) > 1:
                intervals = np.diff(timestamps)
                episode_result["frame_intervals"] = intervals.tolist()

                mean_interval = np.mean(intervals)
                std_interval = np.std(intervals)
                min_interval = np.min(intervals)
                max_interval = np.max(intervals)

                episode_result["mean_interval"] = float(mean_interval)
                episode_result["std_interval"] = float(std_interval)
                episode_result["min_interval"] = float(min_interval)
                episode_result["max_interval"] = float(max_interval)
                episode_result["fps"] = float(1.0 / mean_interval) if mean_interval > 0 else float("inf")

                top_large_idx = np.argsort(intervals)[-3:][::-1]
                top_small_idx = np.argsort(intervals)[:3]
                episode_result["largest_intervals"] = [
                    {"idx": int(i), "interval": float(intervals[i])}
                    for i in top_large_idx
                ]
                episode_result["smallest_intervals"] = [
                    {"idx": int(i), "interval": float(intervals[i])}
                    for i in top_small_idx
                ]

                interval_collections.append(intervals)

                large_gaps = np.where(intervals > max_frame_interval)[0]
                episode_result["num_large_gaps"] = int(len(large_gaps))
                if len(large_gaps) > 0:
                    worst_large_idx = int(large_gaps[np.argmax(intervals[large_gaps])])
                    worst_large_val = float(intervals[worst_large_idx])
                    episode_result["issues"].append(
                        f"{len(large_gaps)} frame gaps exceed {_format_interval_ms(max_frame_interval)}; "
                        f"worst at idx {worst_large_idx}: {worst_large_val:.3f}s"
                    )
                    results["warnings"].append(
                        f"{demo_key}: {len(large_gaps)} gaps > {_format_interval_ms(max_frame_interval)} "
                        f"(worst idx {worst_large_idx}, {worst_large_val:.3f}s)"
                    )
                    issue_counts["large_gaps"] += len(large_gaps)

                tiny_interval_threshold = min_frame_interval * 0.5
                small_intervals = np.where(intervals < tiny_interval_threshold)[0]
                episode_result["num_small_intervals"] = int(len(small_intervals))
                if len(small_intervals) > 0:
                    worst_small_idx = int(small_intervals[np.argmin(intervals[small_intervals])])
                    worst_small_val = float(intervals[worst_small_idx])
                    episode_result["issues"].append(
                        f"{len(small_intervals)} intervals below {_format_interval_ms(tiny_interval_threshold)}; "
                        f"smallest at idx {worst_small_idx}: {_format_interval_ms(worst_small_val)}"
                    )
                    results["warnings"].append(
                        f"{demo_key}: {len(small_intervals)} tiny intervals < "
                        f"{_format_interval_ms(tiny_interval_threshold)} "
                        f"(smallest idx {worst_small_idx}, {_format_interval_ms(worst_small_val)})"
                    )
                    issue_counts["small_intervals"] += len(small_intervals)

                duplicates = np.where((intervals >= 0) & (intervals < 0.001))[0]
                episode_result["num_duplicates"] = int(len(duplicates))
                if len(duplicates) > 0:
                    episode_result["issues"].append(
                        f"Duplicate frames at indices: {duplicates.tolist()}"
                    )
                    results["valid"] = False
                    results["errors"].append(
                        f"{demo_key}: Found {len(duplicates)} duplicate frames"
                    )
                    issue_counts["duplicates"] += len(duplicates)

                out_of_order = np.where(intervals < 0)[0]
                episode_result["num_out_of_order"] = int(len(out_of_order))
                if len(out_of_order) > 0:
                    episode_result["issues"].append(
                        f"Out-of-order timestamps at indices: {out_of_order.tolist()}"
                    )
                    results["valid"] = False
                    results["errors"].append(
                        f"{demo_key}: Found {len(out_of_order)} out-of-order timestamps"
                    )
                    issue_counts["out_of_order"] += len(out_of_order)
            else:
                single_frame_episodes += 1
                episode_result["issues"].append("Only one frame")
                results["warnings"].append(f"{demo_key}: Single frame episode")

            if episode_result["issues"]:
                episodes_with_issues += 1
            results["episodes"].append(episode_result)

        total_duration = float(sum(ep["duration"] for ep in results["episodes"]))
        summary = {
            "episode_groups": num_demos,
            "episodes_with_timestamp": episodes_with_timestamp,
            "episodes_analyzed": len(results["episodes"]),
            "empty_episodes": empty_episodes,
            "single_frame_episodes": single_frame_episodes,
            "episodes_with_issues": episodes_with_issues,
            "total_frames": total_frames,
            "total_duration": total_duration,
            "issue_counts": issue_counts,
        }

        if len(interval_collections) > 0:
            all_intervals = np.concatenate(interval_collections)
            summary["global_interval_stats"] = {
                "mean": float(np.mean(all_intervals)),
                "std": float(np.std(all_intervals)),
                "min": float(np.min(all_intervals)),
                "max": float(np.max(all_intervals)),
                "p50": float(np.percentile(all_intervals, 50)),
                "p95": float(np.percentile(all_intervals, 95)),
                "p99": float(np.percentile(all_intervals, 99)),
            }

        results["summary"] = summary

        if verbose:
            print("\n=== Dataset Details ===")
            print(f"File: {h5_path}")
            print(f"Episode groups: {summary['episode_groups']}")
            print(
                "Episodes analyzed: "
                f"{summary['episodes_analyzed']} "
                f"(with timestamp: {summary['episodes_with_timestamp']}, "
                f"empty: {summary['empty_episodes']}, single frame: {summary['single_frame_episodes']})"
            )
            print(
                f"Total frames: {summary['total_frames']}, "
                f"total duration: {summary['total_duration']:.2f}s"
            )
            print(
                "Issue counts: "
                f"large_gaps={issue_counts['large_gaps']}, "
                f"small_intervals={issue_counts['small_intervals']}, "
                f"duplicates={issue_counts['duplicates']}, "
                f"out_of_order={issue_counts['out_of_order']}"
            )

            global_stats = summary.get("global_interval_stats")
            if global_stats is not None:
                print(
                    "Global interval: "
                    f"{_format_interval_ms(global_stats['mean'])} ± {_format_interval_ms(global_stats['std'])}, "
                    f"range [{_format_interval_ms(global_stats['min'])}, {_format_interval_ms(global_stats['max'])}], "
                    f"p95={_format_interval_ms(global_stats['p95'])}, "
                    f"fps~{_format_fps(global_stats['mean'])}"
                )

            for ep in results["episodes"]:
                print(f"\n  {ep['name']}")
                print(
                    f"    Frames: {ep['num_frames']}, duration: {ep['duration']:.2f}s, "
                    f"time range: [{ep['start_time']:.3f}, {ep['end_time']:.3f}]"
                )
                if "mean_interval" in ep:
                    print(
                        "    Interval: "
                        f"{_format_interval_ms(ep['mean_interval'])} ± {_format_interval_ms(ep['std_interval'])}, "
                        f"fps~{_format_fps(ep['mean_interval'])}"
                    )
                    print(
                        "    Interval range: "
                        f"[{_format_interval_ms(ep['min_interval'])}, {_format_interval_ms(ep['max_interval'])}]"
                    )
                    print(
                        "    Flagged counts: "
                        f"gaps={ep.get('num_large_gaps', 0)}, "
                        f"tiny={ep.get('num_small_intervals', 0)}, "
                        f"dup={ep.get('num_duplicates', 0)}, "
                        f"ooo={ep.get('num_out_of_order', 0)}"
                    )
                    largest = ", ".join(
                        f"idx {item['idx']}: {_format_interval_ms(item['interval'])}"
                        for item in ep.get("largest_intervals", [])
                    )
                    smallest = ", ".join(
                        f"idx {item['idx']}: {_format_interval_ms(item['interval'])}"
                        for item in ep.get("smallest_intervals", [])
                    )
                    if largest:
                        print(f"    Top gaps: {largest}")
                    if smallest:
                        print(f"    Top tiny: {smallest}")
                if ep["issues"]:
                    print("    Issues:")
                    for issue in ep["issues"]:
                        print(f"      - {issue}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate HDF5 dataset quality")
    parser.add_argument("h5_path", help="Path to HDF5 file")
    parser.add_argument(
        "-m", "--max-interval", type=float, default=0.1,
        help="Max frame interval (s). Default: 0.1"
    )
    parser.add_argument(
        "-n", "--min-interval", type=float, default=0.01,
        help="Min expected frame interval (s). Default: 0.01"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    results = validate_dataset(
        args.h5_path,
        max_frame_interval=args.max_interval,
        min_frame_interval=args.min_interval,
        verbose=args.verbose,
    )

    print("\n=== Validation Results ===")
    if results["valid"]:
        print("Status: PASS")
    else:
        print("Status: FAIL")

    print(
        "Thresholds: "
        f"max interval={_format_interval_ms(args.max_interval)}, "
        f"tiny threshold={_format_interval_ms(args.min_interval * 0.5)}"
    )

    summary = results.get("summary", {})
    if summary:
        print("\nDataset summary:")
        print(
            f"  - Episode groups: {summary.get('episode_groups', 0)}; "
            f"analyzed: {summary.get('episodes_analyzed', 0)}"
        )
        print(
            f"  - Episodes with timestamp: {summary.get('episodes_with_timestamp', 0)}; "
            f"empty: {summary.get('empty_episodes', 0)}; "
            f"single frame: {summary.get('single_frame_episodes', 0)}"
        )
        print(
            f"  - Total frames: {summary.get('total_frames', 0)}; "
            f"duration: {summary.get('total_duration', 0.0):.2f}s"
        )
        issue_counts = summary.get("issue_counts", {})
        print(
            "  - Issues: "
            f"large_gaps={issue_counts.get('large_gaps', 0)}, "
            f"small_intervals={issue_counts.get('small_intervals', 0)}, "
            f"duplicates={issue_counts.get('duplicates', 0)}, "
            f"out_of_order={issue_counts.get('out_of_order', 0)}"
        )

        global_stats = summary.get("global_interval_stats")
        if global_stats is not None:
            print(
                "  - Global interval: "
                f"{_format_interval_ms(global_stats['mean'])} ± {_format_interval_ms(global_stats['std'])}, "
                f"range [{_format_interval_ms(global_stats['min'])}, {_format_interval_ms(global_stats['max'])}], "
                f"p95={_format_interval_ms(global_stats['p95'])}, "
                f"fps~{_format_fps(global_stats['mean'])}"
            )

    if results["errors"]:
        print(f"\nErrors ({len(results['errors'])}):")
        for e in results["errors"]:
            print(f"  - {e}")

    if results["warnings"]:
        print(f"\nWarnings ({len(results['warnings'])}):")
        for w in results["warnings"]:
            print(f"  - {w}")

    if "num_episodes" in results:
        print(f"\nTotal episodes: {results['num_episodes']}")

    sys.exit(0 if results["valid"] else 1)


if __name__ == "__main__":
    main()
