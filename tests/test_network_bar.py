import unittest
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kitty/.config/kitty'))
import tab_bar as net


class NetworkTests(unittest.TestCase):
    def linux_fixture(self, directory, names):
        root = Path(directory)
        proc, devices = root / "proc", root / "devices"
        proc.mkdir()
        devices.mkdir()
        rows = ["Inter-| Receive | Transmit", " face | bytes packets errs drop fifo frame compressed multicast | bytes packets errs drop fifo colls carrier compressed"]
        for name, rx, tx in names:
            rows.append(f" {name}: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0")
        (proc / "dev").write_text("\n".join(rows))
        return proc, devices

    def test_linux_physical_interfaces_exclude_virtual_and_keep_64bits(self):
        with TemporaryDirectory() as directory:
            proc, devices = self.linux_fixture(directory, [
                ("enp1s0", 2 ** 40, 2 ** 41), ("wlan0", 50, 60),
                ("lo", 999, 999), ("docker0", 999, 999), ("wg0", 999, 999), ("veth0", 999, 999)])
            for name in ("enp1s0", "wlan0"):
                (devices / name / "device").mkdir(parents=True)
            self.assertEqual(net.read_linux_counters(proc, devices),
                             {"enp1s0": (2 ** 40, 2 ** 41), "wlan0": (50, 60)})

    def test_linux_namespace_uses_one_lowest_metric_default_interface(self):
        with TemporaryDirectory() as directory:
            proc, devices = self.linux_fixture(directory, [("eth0", 10, 20), ("eth1", 30, 40), ("lo", 99, 99)])
            (proc / "route").write_text("Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
                                       "eth0 00000000 0100000A 0003 0 0 100 00000000 0 0 0\n"
                                       "eth1 00000000 0100000A 0003 0 0 50 00000000 0 0 0\n"
                                       "eth0 00000000 0100000A 0003 0 0 0 00000080 0 0 0\n"
                                       "eth0 00000000 0100000A 0000 0 0 0 00000000 0 0 0\n")
            self.assertEqual(net.read_linux_counters(proc, devices), {"eth1": (30, 40)})

    def test_linux_ipv6_only_namespace_and_no_route(self):
        with TemporaryDirectory() as directory:
            proc, devices = self.linux_fixture(directory, [("eth0", 10, 20)])
            self.assertEqual(net.read_linux_counters(proc, devices), {})
            (proc / "ipv6_route").write_text(f"{'0' * 32} 00 {'0' * 32} 00 {'0' * 32} 00000064 00000000 00000000 00000003 eth0\n")
            self.assertEqual(net.read_linux_counters(proc, devices), {"eth0": (10, 20)})

    def test_linux_malformed_stats_are_unavailable(self):
        with TemporaryDirectory() as directory:
            proc, devices = self.linux_fixture(directory, [("eth0", "invalid", 20), ("eth1", -10, 20)])
            (devices / "eth0" / "device").mkdir(parents=True)
            self.assertEqual(net.read_linux_counters(proc, devices), {})

    def test_panel_color_order_length_units_and_stable_width(self):
        samples = [(59, 1_000_000, 250_000), (60, 0, 0)]
        for platform in ("darwin", "linux"):
            for columns in (60, 100, 120, 155, 250):
                widths = []
                for status in ("ready", "starting", "unavailable"):
                    segments, width = net.format_panel((samples, 1_000_000, 250_000, status), columns, 60, platform)
                    rendered = "".join(text for _, text in segments)
                    self.assertEqual(len(rendered), width)
                    self.assertNotIn("60s", rendered)
                    self.assertNotIn("≤", rendered)
                    widths.append(width)
                    if status != "unavailable":
                        self.assertEqual(segments[1][0], 0xa3be8c)
                        self.assertEqual(segments[2][0], 0x88c0d0)
                        count = 6 if columns < 120 else 8
                        self.assertTrue(segments[1][1].startswith("↓"))
                        self.assertTrue(segments[2][1].startswith("↑"))
                        self.assertEqual(len(segments[1][1][1:1 + count]), count)
                        self.assertEqual(rendered.count("b/s"), 0 if columns < 120 else 2)
                self.assertEqual(len(set(widths)), 1)

    def test_only_physical_interfaces_and_full_64bit_counts(self):
        names = {1: 'en0', 2: 'en1', 3: 'utun0', 4: 'bridge100', 5: 'lo0'}
        output = b''
        for index in names:
            message = net.InterfaceMibData()
            message.name = names[index].encode()
            message.data.ibytes = 2 ** 40 + index
            message.data.obytes = 2 ** 41 + index
            output += bytes(message)
        self.assertEqual(net.parse_counters(output),
                         {'en0': (2 ** 40 + 1, 2 ** 41 + 1), 'en1': (2 ** 40 + 2, 2 ** 41 + 2)})

    def test_invalid_binary_snapshot_does_not_loop_or_read_past_buffer(self):
        for output in (b'\x00\x00\x00\x12', b'\xff\xff\x00\x12'):
            with self.assertRaises(ValueError):
                net.parse_counters(output)

    def test_bytes_to_bits_per_second_and_no_new_interface_spike(self):
        history = net.NetworkHistory()
        history.update({"en0": (1000, 2000)}, 10)
        history.update({"en0": (1500, 2100), "en1": (900000, 700000)}, 12)
        self.assertEqual((history.rx, history.tx), (2000, 400))
        self.assertEqual(history.status, "ready")

    def test_counter_reset_is_not_negative_traffic(self):
        history = net.NetworkHistory()
        history.update({"en0": (1000, 2000)}, 1)
        history.update({"en0": (10, 20)}, 2)
        self.assertEqual(history.status, "starting")
        history.update({"en0": (110, 70)}, 3)
        self.assertEqual((history.rx, history.tx), (800, 400))

    def test_sleep_gap_and_failed_measurement(self):
        history = net.NetworkHistory()
        history.update({"en0": (100, 100)}, 1)
        history.update({"en0": (10000, 10000)}, 50)
        self.assertEqual(history.status, "starting")
        self.assertFalse(history.samples)
        history.update({}, 51)
        self.assertEqual(history.status, "unavailable")
        self.assertIsNone(history.previous)

    def test_chart_preserves_bursts_and_uses_shared_scale(self):
        graphs, scale = net.chart_data([(59, 1_000_000, 250_000), (60, 0, 0)], 60, 12)
        self.assertEqual(scale, 1_000_000)
        self.assertEqual(graphs[0][-1], "█")
        self.assertNotEqual(graphs[1][-1], "█")
        self.assertEqual(graphs[0][0], "·")

    def test_chart_expires_old_peaks_and_distinguishes_unknown_from_zero(self):
        graphs, scale = net.chart_data([(0, 10_000_000, 0), (60, 0, 0)], 60, 12)
        self.assertEqual(scale, 100_000)
        self.assertEqual(graphs[0], "·" * 11 + "▁")

    def test_rate_fits_fixed_cells(self):
        for value in (0, 5, 999, 99_949, 99_999, 999_999, 99_999_999, 1_000_000_000):
            self.assertLessEqual(len(net.compact_rate(value)), 5)

    def test_width_budget_for_eight_tabs_and_narrow_windows(self):
        for available in (0, 10, 36, 92, 160):
            widths = net.allocate_widths([14, 16, 12, 20, 18, 10, 24, 23], 7, available)
            self.assertLessEqual(sum(widths), available)
            self.assertTrue(all(width >= 0 for width in widths))
        self.assertGreaterEqual(net.allocate_widths([20] * 8, 7, 92)[7], 20)


if __name__ == "__main__":
    unittest.main()
