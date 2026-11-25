import unittest

from scripts.conducted_power_reference import power_basis


class PowerBasisTest(unittest.TestCase):
    def test_known_loss_and_cancellation(self):
        doc = dict(schema="conducted-power-reference/1", source_sha256="a"*64,
                   carrier_hz=2e9, bandwidth_hz=1e6, tx_power_dbm={"0": 10}, links={"0/0":dict(coefficient_unit="power_wave_ratio",relative_ray_phase="preserved",
                   tx_plane="发射馈口", rx_plane="接收馈口", phase_origin="载频",
                   delay_origin="传播时间", included_losses="自由空间",
                   antenna_response="both")})
        manifest, rows = power_basis(doc, "a"*64, 2e9, [0],[0], {(0,0): [[.1+0j],[1,-1]]}, [2,3])
        self.assertAlmostEqual(rows[0]["single_tx_carrier_dbm"], -10)
        self.assertEqual(rows[1]["carrier_power_ratio"], 0)
        self.assertIsNone(rows[1]["single_tx_carrier_dbm"])
        self.assertFalse(manifest["formal_measurement"])
        doc["links"]["0/0"].update(coefficient_unit="voltage_transfer_ratio",tx_impedance_ohm=50,rx_impedance_ohm=100)
        _, rows = power_basis(doc,"a"*64,2e9,[0],[0,1],{(0,0):[[1]],(0,1):[[1]]},[0])
        self.assertAlmostEqual(rows[0]["single_tx_carrier_dbm"],6.98970004)
        self.assertIsNone(rows[1]["single_tx_carrier_dbm"])
        doc["links"]["0/0"]["relative_ray_phase"]="unknown"
        _, rows = power_basis(doc,"a"*64,2e9,[0],[0],{(0,0):[[1,1]]},[0])
        self.assertIsNone(rows[0]["carrier_coefficient_norm_squared"])
        with self.assertRaises(ValueError):
            power_basis(doc, "b"*64, 2e9, [0],[0], {}, [])

    def test_unknown(self):
        m,r=power_basis(None,"a"*64,2e9,[0],[0],{(0,0):[[1]]},[2])
        self.assertIsNone(r[0]["single_tx_carrier_dbm"])
        self.assertIsNone(m["tx_power_dbm"])
