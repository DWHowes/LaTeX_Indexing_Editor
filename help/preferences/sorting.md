# The Sorting Page

**Edit → Preferences → Sorting** holds everything that decides where a heading files. It opens with [what kind of index this is](index_kind.md), which fills the settings below it with sensible defaults for that kind, and further down it holds the [declared alphabet](declared_alphabets.md). This topic covers the setting between them, **Which order to show**, and says where the rest are explained.

## Which order to show

**No index engine lets a tool choose its sort strategy, and the engines disagree with each other**, so the order you want and the order your finished index will have are two different lists. This setting decides which of the two the [index tree](../index_tree/navigating.md) shows you.

- **By this project's rules** shows the order you are working to, with everything set on this page: the alphabetising strategy, numbers, Roman numerals, prefixes, a declared alphabet. This is the default.
- **As this format will actually file it** shows the order the index engine will give the finished index, as measured against the engine itself. Which engine is the one chosen under [Index Engine](latex_settings/index_engine.md):
  - **makeindex** files word by word or letter by letter as its Sort Ordering Rule says, reads numbers as characters, and **does not fold accents**: *Ára* and *áit* file after *z*.
  - **xindy** files an ordinary accented letter beside its base letter, so *José* files beside *Josef* and *Müller* beside *Muller*, exactly as Word does. Characters outside its collation, such as *Ḥ* or *ʿ*, are not folded and can land well away from their base letter.

**Use the second to see what the publisher will print**, and the first to see what you intended. Where the two differ, a sort key on that entry is what brings the printed index into line with your rules.

**The setting changes what you see and never what is written.** Every entry, and every macro a [Table of Authorities](../tools/table_of_authorities.md) run writes, is filed by this project's own rules whichever answer is chosen here. Until 8 October 2026 a Table of Authorities run used the order shown here instead, which with xindy chosen could write a folded sort key that merged two entries into one.

## The rest of the page

- **What kind of index is this?** See [What Kind of Index Is This?](index_kind.md).
- **Alphabetising.** The strategy is shown here and set under **LaTeX → cmd: makeindex/xindy → Sort Ordering Rule**, so that it is stored once. The checkboxes beside it file numbers and regnal Roman numerals by value, *Mc* as *Mac*, and an Irish woman's name on the unlenited form.
- **File something as something else.** Applied before every other rule on the page: the [declared alphabet](declared_alphabets.md), alphabets by language, and substitutions that file one spelling as another (a number as words, an abbreviation as what it stands for).
- **What to ignore when filing.** Hyphens and slashes, punctuation, parenthetical phrases and endings, accents, and the prefixes a heading or subheading is not filed on, which [Name Inversion](../additional/name_inversion.md) explains.
- **Which characters file first.** Whether symbols, digits or letters lead.

## See also

- [Preferences](../preferences.md)
- [Viewing and Navigating the Index Tree](../index_tree/navigating.md)
