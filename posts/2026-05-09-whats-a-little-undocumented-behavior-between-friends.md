---
title: What's a little undocumented behavior between friends?
date: 2026-05-09 15:51
tags: General
---

(NOTE: this post will get very technical.  Some knowledge of 16-bit x86 assembly will help).

From the [MPC60](https://en.wikipedia.org/wiki/Akai_MPC) code that computes the duration of a note in timer ticks:

```
seg000:5659                 sub     dx, dx
seg000:565B                 mov     cx, 0Ah
seg000:565E                 div     cx
seg000:5660                 jnz     short loc_5665
seg000:5662                 mov     ax, 1
seg000:5665
seg000:5665 loc_5665:
seg000:5665                 mov     bx, ax
```

This was falling through the JNZ and giving a result of 1 every time, which doesn't sound very good (the timer rate was around 290 Hz in this case, but it seems to depend on the current sequencer tempo).  What influences the JNZ?  It's like this:

1. SUB DX, DX zeros out DX and sets the zero flag
2. MOV CX, 0Ah loads CX and doesn't affect any flags
3. DIV CX does a division and is documented by Intel to have undefined effects on the zero flag.  MAME i86.cpp expresses this as doing nothing to the flag, but we could also validly have set it to a random value according to that documentation.

So the zero flag was always set, and the JNZ always fell through, turning every sample into a short click.

It turns out that in the 80s it was known by some that the zero flag was set according to the quotient, so it's cleared if the quotient isn't 0.  Roger Linn was apparently one of the people who knew, because it's used multiple places in the MPC60 firmware.

But now that [Ken Shirriff](https://righto.com/) has dumped the 8086 and 8088 microcode, and you can run the microcode in order to run 8088 MPH and Area 5150 cycle-perfect in the [XTCE-Blue emulator](https://github.com/dbalsom/XTCE-Blue), we know that it's not quite that way.  Internally, the 8086 and 8088 use, essentially, [long division](https://www.righto.com/2023/04/reverse-engineering-8086-divide-microcode.html) with a series of subtracts.  As a side effect of this, in most cases the zero flag is set as you'd expect with respect to the quotient of the DIV or IDIV instruction: set if the quotient is zero, cleared if not.

So what's meant to happen is that you get a non-zero quotient (because you always will given constraints on the inputs here), the zero flag is cleared, the JNZ is taken, and [everything works fine](https://www.youtube.com/watch?v=blLbiFYYQzo), plus or minus.
