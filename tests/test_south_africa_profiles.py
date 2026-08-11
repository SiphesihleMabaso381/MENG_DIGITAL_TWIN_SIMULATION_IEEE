import unittest

from src.load_profiles import CustomerType, get_recommended_customer_types


class SouthAfricaProfileTests(unittest.TestCase):
    def test_recommended_customer_types_stay_simple(self):
        recommended = get_recommended_customer_types()

        self.assertEqual(
            recommended,
            [
                CustomerType.RESIDENTIAL,
                CustomerType.COMMERCIAL,
                CustomerType.INDUSTRIAL,
                CustomerType.AGRICULTURAL,
                CustomerType.PUBLIC_MUNICIPAL,
                CustomerType.INSTITUTIONAL,
                CustomerType.BULK,
            ],
        )


if __name__ == "__main__":
    unittest.main()
