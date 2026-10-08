r"""
The User Guide's three populated sidebar figures, from the real application.

**Not a test**, and named so that the suite never collects it. It lives here
because it needs this directory's fixtures (`booted_app`, `open_project`): the
index tree, the entry table and the Cross-References tab are filled by the
controllers, so the honest way to photograph them is to open a project.
`probes/shoot_screenshots.py` takes every other figure.

The project is **invented**, a short book on negligence, because the July
figures showed a test book's own index, which the suite's rule on client
text forbids in a committed file.

Run it on the real platform, which is what the guide's other figures use:

    set QT_QPA_PLATFORM=windows
    .venv\Scripts\python.exe -m pytest tests/gui_smoke/shoot_guide_panels.py -o addopts="" -s

It writes into `documentation/images/`, or into the folder named by
`SHOOT_OUT` when that is set, so a batch can be looked at before it replaces
anything.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHAPTERS = {
    "1.Duty/chapter1.tex": r"""\chapter{The Duty of Care}
\index{duty of care|(}\index{Donoghue v Stevenson}\index{neighbour principle}
The duty of care began with a snail.\index{duty of care!proximity}
\index{foreseeability}\index{foreseeability!reasonable person}
\index{reasonable person standard}\index{duty of care!policy}
\index{economic loss}\index{economic loss!pure}\index{nervous shock}
\index{nervous shock!primary victims}\index{nervous shock!secondary victims}
\index{omissions}\index{omissions!rescuers}\index{public authorities}
\index{duty of care|)}
""",
    "2.Breach/chapter2.tex": r"""\chapter{Breach}
\index{breach of duty}\index{breach of duty!standard of care}
\index{breach of duty!professionals}\index{Bolam test}\index{Bolitho v City and Hackney}
\index{standard of care}\index{standard of care!children}
\index{standard of care!learners}\index{res ipsa loquitur}\index{risk!magnitude}
\index{risk!cost of precautions}\index{social utility}
""",
    "3.Causation/chapter3.tex": r"""\chapter{Causation}
\index{causation}\index{causation!but-for test}\index{causation!material contribution}
\index{Barnett v Chelsea and Kensington}\index{loss of chance}
\index{novus actus interveniens}\index{remoteness of damage}
\index{remoteness of damage!eggshell skull}\index{Wagon Mound}
\index{multiple causes}
""",
    "4.Defences/chapter4.tex": r"""\chapter{Defences}
\index{contributory negligence}\index{contributory negligence!apportionment}
\index{volenti non fit injuria}\index{illegality}\index{limitation periods}
\index{exclusion of liability}\index{comparative fault}
""",
}

#: Managed cross-references, added through the tab's own controller.
CROSS_REFERENCES = [
    ("Bolam test", "see also", "breach of duty"),
    ("comparative fault", "see", "contributory negligence"),
    ("Donoghue v Stevenson", "see also", "neighbour principle"),
    ("economic loss", "see also", "duty of care"),
    ("foreseeability", "see also", "remoteness of damage"),
    ("illegality", "see also", "volenti non fit injuria"),
    ("loss of chance", "see also", "causation"),
    ("nervous shock", "see also", "duty of care"),
    ("res ipsa loquitur", "see also", "breach of duty"),
    ("risk", "see also", "standard of care"),
    ("Wagon Mound", "see", "remoteness of damage"),
]


def _book(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.tex").write_text(
        "\\documentclass{book}\n\\usepackage{imakeidx}\n\\makeindex\n"
        "\\begin{document}\n"
        + "".join(f"\\input{{{name}}}\n" for name in CHAPTERS)
        + "\\printindex\n\\end{document}\n", encoding="utf-8")
    for name, text in CHAPTERS.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return folder


def test_shoot_the_populated_sidebar(booted_app, qtbot, monkeypatch, tmp_path, open_project):
    out = Path(os.environ.get("SHOOT_OUT") or ROOT / "documentation" / "images")
    out.mkdir(parents=True, exist_ok=True)
    project = _book(tmp_path / "The Law of Negligence")
    pipeline = booted_app.pipeline_controller
    open_project(qtbot, monkeypatch, pipeline, str(project), "The Law of Negligence")

    for source, kind, target in CROSS_REFERENCES:
        pipeline.cross_reference_ctrl._on_add_requested(
            source, "see" if kind == "see" else "seealso", target)

    sidebar = pipeline.sidebar_view_panel
    sidebar.show()

    def shoot(name, size):
        sidebar.resize(*size)
        qtbot.wait(150)
        sidebar.grab().save(str(out / f"{name}.png"))
        print(f"  {name} {size[0]}x{size[1]} -> {out}")

    sidebar.setCurrentIndex(1)
    # Wide enough to read the headings; the column's default truncates most
    # of them, which the July figure showed too.
    sidebar.tree_index.header().resizeSection(0, 340)
    shoot("sidebar_index_references_populated", (700, 760))
    sidebar.setCurrentIndex(2)
    sidebar.edit_entries_tabs.setCurrentIndex(0)
    shoot("sidebar_edit_entries_populated new", (860, 760))
    sidebar.edit_entries_tabs.setCurrentIndex(1)
    shoot("sidebar_edit_xrefs", (690, 520))
