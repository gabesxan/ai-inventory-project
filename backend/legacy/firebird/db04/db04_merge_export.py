"""DB-04 follow-up · merge a re-exported table into the complete export (stdlib, host side).

    python3 db04_merge_export.py <full-a> <full-a-meta> <part> <part-meta>

``part`` is an export of the table(s) that failed in ``full-a`` (for example with ``--lenient-decode``). The
table directory is copied in, the manifest gains its entry with a provenance note, the failure is removed from
``errors`` and ``counts.tsv`` is updated. ``complete`` becomes true only when no error is left and both
snapshots are the same (same .fbk sha256). The result must still pass ``python -m legacy.manifest validate``.
"""
import json
import os
import shutil
import sys


def main(full, full_meta, part, part_meta):
    mf, mp = (json.load(open(os.path.join(d, "manifest.json"))) for d in (full, part))
    if mf["source"]["snapshot_fbk_sha256"] != mp["source"]["snapshot_fbk_sha256"]:
        sys.exit("refusing to merge: the two exports come from different snapshots")
    failed = {e["table"] for e in mf["errors"]}
    for table, entry in mp["tables"].items():
        if table not in failed:
            sys.exit("refusing to merge %s: it did not fail in the main export" % table)
        if os.path.exists(os.path.join(full, table)):
            sys.exit("%s already exists in the main export" % table)
        shutil.copytree(os.path.join(part, table), os.path.join(full, table))
        entry = dict(entry, merged_from="re-export of the failed table (%s)" % mp["run"]["extracted_at_utc"])
        mf["tables"][table] = entry
    mf["errors"] = [e for e in mf["errors"] if e["table"] not in mp["tables"]]
    mf["complete"] = not mf["errors"]
    tmp = os.path.join(full, "manifest.json.tmp")
    with open(tmp, "w") as f:
        json.dump(mf, f, indent=1, sort_keys=True)
    os.rename(tmp, os.path.join(full, "manifest.json"))

    path = os.path.join(full_meta, "counts.tsv")
    rows = [l.rstrip("\n").split("\t") for l in open(path)]
    new = dict((l.split("\t")[0], l.rstrip("\n").split("\t")) for l in open(os.path.join(part_meta, "counts.tsv")).readlines()[1:])
    with open(path, "w") as f:
        for r in rows:
            f.write("\t".join(new.get(r[0], r)) + "\n")
    with open(os.path.join(full_meta, "errors.log"), "w") as f:
        for e in mf["errors"]:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    print("merged %s; tables=%d errors=%d complete=%s" % (sorted(mp["tables"]), len(mf["tables"]), len(mf["errors"]), mf["complete"]))


if __name__ == "__main__":
    main(*sys.argv[1:5])
