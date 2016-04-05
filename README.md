This is a work-in-progress collection of tests for the Inform 6 library. The intent is to fill in all of the exercises from the DM4, plus any ad-hoc cases that seem desirable for testing library features.

To run these tests, you must have:

- The Inform 6 compiler.
- Glulx and Z-code interpreters compiled with the RemGlk library.
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
[Fizmo]: https://christoph-ender.de/fizmo/

To run the same tests in Z-code (where `fizmor` is [Fizmo][]+[RemGlk][]):

    python3 dotest.py -Z --terp fizmor */*.inf

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

The test looks like a partial game transcript: a sequence of commands and responses. (With an extra "response" on top, which is the game's initial output.)

However, this is not a simple literal output match! Each "response" line is checked separately. The script will check that that line occurs *somewhere in* the game's output from the relevant command. It does not have to be a complete line. For the sample above, the game's opening text might be

    The game begins here with some initial text. Then more
    initial text will appear.

The phrases `some initial text` and `more initial text` both appear, so the test will pass. Subsequent commands are checked in the same way.

Note that checks are *independent*. If you write:

    > i
    gold ring
    silver coin

...then you're checking for those two lines, but not their order. (This is a good thing; you generally don't care about the order of inventory output.)

The line

    {count=3} coin

...will check that the word `coin` occurs at least three times in the output. (Note that repeating the test line `coin` three times is not sufficient. That would just triple-check for the word, which is a waste of time.)

A check line starting with "!" is negated. A check line starting with "/" is a regular expression. If you write:

    > north
    /(Red|Green|Blue) Chamber
    !grue

...then the script would check that the result of the `north` command included *any* of the phrases `Red Chamber`, `Green Chamber`, `Blue Chamber`, and also did *not* contain the word `grue`. (Yes, you can write `!/` for a negated regexp. You can also write `!{count=...}`. But you can't combine the regexp and count formats, sorry.)

You can include several tests, each starting with an asterisk line:

    * testname

Each test should have a different name. Each test is a separate playthrough, starting from the beginning of the game.

For more information about the text syntax, see the [RegTest][] documentation.

[RegTest]: http://eblong.com/zarf/plotex/regtest.html

## Contributing

### The `dm4/` directory: exercises

Pick an exercise from the [DM4][] and write a file named `ex-$NUM.inf`. Paste in exactly the answer code from the DM4 page, plus enough framework that you can run the game and demonstrate that the exercise works.

Include one or more tests which demonstrate the behavior. Try to cover all aspects of the exercise, including both commands which should work and commands which should fail.

Otherwise follow the format in existing tests:

- Use `"Example $NUM"` as the `Story` header and `"^"` as the `Headline`.
- We're only compiling to Glulx. If an exercise is really Z-code-only, skip it.
- Spaces, not tabs.
- Keep the framework simple. (Some exercises are based on the _Ruins_ sample game from the DM4. You can include more code from _Ruins_ in your test if it makes sense, but you can also trim it down.)
- Abbreviate test outputs where possible. If your test includes a movement command, just check for the name of the destination room, not the room description. If the example code writes a paragraph of static output, just check for the first phrase.
- If the test output is randomized, use regexp checks to cover all the possibilities.
- One test (asterisk line) is usually sufficient. But it's better to write two tests than to rely on `RESTART` or `UNDO` commands in your test script.

### The `general/` directory

Pick a library feature and write a test that covers it. I haven't gone through and come up with a list of features we want to cover.

### The `bugs/` directory

Pick a bug and write a test that demonstrates that it doesn't work. (The test should check for the *desired* output, so the test will fail.)

The [I6 Known Problems][i6bug] page is a good source of bugs which are being fixed for 6/12. But I'm sure there are more.
