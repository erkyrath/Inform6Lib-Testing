This is a work-in-progress collection of tests for the Inform 6 library. The intent is to fill in all of the exercises from the DM4, plus any ad-hoc cases that seem desirable for testing library features.

To run these tests, you must have:

- The Inform 6 compiler.
- A Glulx interpreter compiled with the RemGlk library.
- The Inform libraries release 6/11. This is set up as a submodule. 

## Running

To populate the `inform6lib` directory with the 6/11 library, type:

    git submodule init
    git submodule update

Then you can run this sort of command (assuming that `inform` is [Inform 6][i6] and `glulxer` is [Glulxe][]+[RemGlk][], and both are available on your `$PATH`):

    python3 dotest.py --terp glulxer */*.inf

[i6]: https://github.com/DavidKinder/Inform6
[Glulxe]: https://github.com/erkyrath/glulxe
[RemGlk]: https://github.com/erkyrath/remglk

## The Tests

- `general/`: Tests for individual features of the I6 library.
- `dm4/`: One test for every example in the [Inform Designer's Manual][DM4].
- `bugs/`: Tests for various known bugs, as listed on the [I6 Known Problems][i6bug] page. Each of these tests will fail!

[DM4]: http://inform-fiction.org/manual/html/sa6.html
[i6bug]: http://inform-fiction.org/patches/library.html

## Test Syntax

Each test file looks like regular Inform 6 source code, except that the source ends with the line

    #END; ! test

This ends compilation and also signals that a list of tests will follow. A test looks like

    * testname
    some initial text
    more initial text
    
    > command
    command response
    
    > another command
    another response
    more from the response

The test looks like a partial game transcript: a sequence of commands and responses. (With an extra "response" on top, which is the game's initial output.) However, this is not a simple literal output match!

Each "response" line is checked separately. The script will check that that line occurs *somewhere in* the game's output from the relevant command. It does not have to be a complete line. For the sample above, the game's opening text might be

    The game begins here with some initial text. Then more
    initial text will appear.

The phrases `some initial text` and `more initial text` both appear, so the test will pass. Subsequent commands are checked in the same way.

Note that checks are *independent*. If you write:

    > i
    gold ring
    silver coin
    silver coin

...then the script will check twice for `silver coin` in the output, which is a waste of time. It is *not* checking that the line appears twice. It also does not check that lines appear in any particular order. (But, for inventory, that's a good thing; you probably don't care about the order.)

A check line starting with "!" is negated. A check line starting with "/" is a regular expression. If you write:

    > north
    /(Red|Green|Blue) Chamber
    !grue

...then the script would check that the result of the `north` command included *any* of the phrases `Red Chamber`, `Green Chamber`, `Blue Chamber`, and also did *not* contain the word `grue`. (Yes, you can write `!/` for a negated regexp.)

For more information about the text syntax, see the [RegTest][] documentation.

[RegTest]: http://eblong.com/zarf/plotex/regtest.html
