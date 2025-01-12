#!/usr/bin/env python3
import argparse
import math
import os
import sys

"""Generate segments according to label."""


class LabelInfo(object):
    def __init__(self, start, end, label_id):
        self.label_id = label_id
        self.start = start
        self.end = end


class SegInfo(object):
    def __init__(self):
        self.segs = []
        self.start = -1
        self.end = -1

    def add(self, start, end, label):
        start = float(start)
        end = float(end)
        if self.start < 0 or self.start > start:
            self.start = start
        if self.end < end:
            self.end = end
        self.segs.append((start, end, label))

    def split(self, threshold=30):
        seg_num = math.ceil((self.end - self.start) / threshold)
        if seg_num == 1:
            return [self.segs]
        avg = (self.end - self.start) / seg_num
        return_seg = []

        start_time = self.start
        cache_seg = []
        for seg in self.segs:
            cache_time = seg[1] - start_time
            if cache_time > avg:
                return_seg.append(cache_seg)
                start_time = seg[0]
                cache_seg = [seg]
            else:
                cache_seg.append(seg)

        return_seg.append(cache_seg)
        return return_seg


def pack_zero(file_id, number, length=4):
    number = str(number)
    return file_id + "_" + "0" * (length - len(number)) + number


def get_parser():
    parser = argparse.ArgumentParser(
        description="Prepare segments from HTS-style alignment files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("scp", type=str, help="scp folder")
    parser.add_argument(
        "--threshold",
        type=int,
        help="threshold for silence identification.",
        default=30000,
    )
    parser.add_argument(
        "--silence", action="append", help="silence_phone", default=["pau"]
    )
    return parser


def make_segment(file_id, labels, threshold=30, sil=["pau", "br", "sil"]):
    segments = []
    segment = SegInfo()
    for i in range(len(labels)):
        label = labels[i]
        # replace wrong phoneme with correct one
        if "01" in file_id and label.label_id == "cl" and labels[i + 1].label_id == "s":
            label.label_id = "a"
        if (
            "03" in file_id
            and label.label_id == "s"
            and labels[i - 1].label_id == "o"
            and labels[i - 2].label_id == "o"
        ):
            label.label_id = "z"
        # remove wrong phoneme
        if "50" in file_id and label.label_id == "o" and labels[i + 1].label_id == "a":
            labels[i + 1].start = label.start
            continue
        if "08" in file_id and label.label_id == "w" and labels[i - 1].label_id == "e":
            labels[i + 1].start = label.start
            continue
        if "01" in file_id and label.label_id == "e" and labels[i + 1].label_id == "e":
            labels[i + 1].start = label.start
            continue
        if "41" in file_id and label.label_id == "a" and labels[i + 1].label_id == "o":
            labels[i + 1].label_id = "a"
            labels[i + 1].start = label.start
            continue
        # add missing phoneme
        if (
            "10" in file_id
            and label.label_id == "a"
            and labels[i + 1].label_id == "a"
            and labels[i + 2].label_id == "o"
        ):
            segment.add(label.start, 81.00, "a")
            label.start = 81.00
        # add pause
        if "03" in file_id and (
            (label.label_id == "m" and labels[i + 1].label_id == "e")
            or (label.label_id == "t" and labels[i + 2].label_id == "d")
        ):
            segments.extend(segment.split(threshold=threshold))
            segment = SegInfo()
        if label.label_id in sil:
            # remove rest
            if i < len(labels) - 1 and (
                (
                    "12" in file_id
                    and labels[i + 1].label_id == "m"
                    and labels[i + 2].label_id == "o"
                )
                or ("31" in file_id and labels[i + 1].label_id == "s")
                or ("26" in file_id and labels[i + 1].label_id == "o")
                or (
                    "10" in file_id
                    and labels[i + 1].label_id == "k"
                    and labels[i + 2].label_id == "i"
                )
                or ("24" in file_id and i == 389)
                or (
                    "07" in file_id
                    and labels[i + 1].label_id == "m"
                    and labels[i - 1].label_id == "o"
                )
            ):
                labels[i + 1].start = label.start
                continue
            if len(segment.segs) > 0:
                segments.extend(segment.split(threshold=threshold))
                segment = SegInfo()
            continue
        segment.add(label.start, label.end, label.label_id)

    if len(segment.segs) > 0:
        segments.extend(segment.split(threshold=threshold))

    segments_w_id = {}
    id = 0
    for seg in segments:
        if len(seg) == 0:
            continue
        segments_w_id[pack_zero(file_id, id)] = seg
        id += 1
    return segments_w_id


if __name__ == "__main__":
    args = get_parser().parse_args()
    args.threshold *= 1e-3
    segments = []

    wavscp = open(os.path.join(args.scp, "wav.scp"), "r", encoding="utf-8")
    label = open(os.path.join(args.scp, "label"), "r", encoding="utf-8")

    update_segments = open(
        os.path.join(args.scp, "segments.tmp"), "w", encoding="utf-8"
    )
    update_label = open(os.path.join(args.scp, "label.tmp"), "w", encoding="utf-8")

    for wav_line in wavscp:
        label_line = label.readline()
        if not label_line:
            raise ValueError("not match label and wav.scp in {}".format(args.scp))

        wavline = wav_line.strip().split(" ")
        recording_id = wavline[0]
        path = " ".join(wavline[1:])
        phn_info = label_line.strip().split()[1:]
        temp_info = []
        # correct capitalization
        for i in range(len(phn_info) // 3):
            if phn_info[i * 3 + 2] == "U":
                phn_info[i * 3 + 2] = "u"
            if phn_info[i * 3 + 2] == "I":
                phn_info[i * 3 + 2] = "i"
            temp_info.append(
                LabelInfo(phn_info[i * 3], phn_info[i * 3 + 1], phn_info[i * 3 + 2])
            )
        segments.append(
            make_segment(recording_id, temp_info, args.threshold, args.silence)
        )

    for file in segments:
        for key, val in file.items():
            segment_begin = "{:.3f}".format(val[0][0])
            segment_end = "{:.3f}".format(val[-1][1])

            update_segments.write(
                "{} {} {} {}\n".format(
                    key, "_".join(key.split("_")[:-1]), segment_begin, segment_end
                )
            )
            update_label.write("{}".format(key))

            for v in val:
                update_label.write(" {:.3f} {:.3f}  {}".format(v[0], v[1], v[2]))
            update_label.write("\n")
