# Tidewatch

A small command-line tool that reads tide tables for a harbour and prints the next high and low water, the
height, and the time to go. It exists because the harbour office publishes the tables as a spreadsheet and
nobody wants to open a spreadsheet at five in the morning.

## Installing

Tidewatch is a single script. Put it somewhere on your path and make it executable:

```sh
curl -O https://example.invalid/tidewatch/tidewatch.sh
chmod +x tidewatch.sh
mv tidewatch.sh ~/.local/bin/tidewatch
```

It needs a POSIX shell and `awk`. Nothing else.

## Usage

```
tidewatch [--port NAME] [--days N] [--json]
```

- `--port` selects the harbour; the default is the one in `~/.config/tidewatch/port`.
- `--days` prints that many days ahead instead of the next event only.
- `--json` prints one object per event for other tools to read.

Without arguments it prints something like:

```
Port Ellen   high  06:42  4.1 m   in 1 h 12 min
Port Ellen   low   12:58  0.7 m   in 7 h 28 min
```

## Tables

The tables live under `~/.config/tidewatch/tables/`, one file per port and year, as tab-separated values with
a header row. The columns are:

| column | meaning                              |
| ------ | ------------------------------------ |
| date   | ISO date of the event                |
| time   | local time, 24-hour clock            |
| kind   | `high` or `low`                      |
| height | metres above chart datum, one decimal |

A table that is missing for the current year makes the tool exit with status 3 and a message naming the file
it looked for.

## Heights and datums

Heights are relative to chart datum, which is the lowest astronomical tide for the port. To convert to the
local land datum add the offset printed in the table's header comment; it differs by port and is usually
between one and three metres.

Predictions do not account for weather. A deep low or a strong onshore wind can add half a metre or more, and
the tool says nothing about that.

## Contributing

Bug reports and tables for other ports are welcome. Keep tables in the same format and name them
`<port>-<year>.tsv`. Please do not send tables copied from a publisher's almanac; those are not ours to share.

## Licence

Tidewatch is released under the MIT licence; see `LICENSE`.
