class MockApiClient:
    """Fake HIS client used for tests."""

    def get_hospitals(self) -> list[str]:
        """Return the available hospitals."""
        return ["Central Hospital", "North Hospital"]

    def get_specialties(self, hospital: str) -> list[str]:
        """Return specialties available at the chosen hospital."""
        if hospital == "Central Hospital":
            return ["Cardiology", "Dermatology"]
        if hospital == "North Hospital":
            return ["Pediatrics", "Traumatology"]
        return []

    def get_doctors(self, hospital: str, specialty: str) -> list[str]:
        """Return doctors depending on hospital and specialty."""
        mapping = {
            ("Central Hospital", "Cardiology"): ["Dr. Garcia", "Dr. Perez"],
            ("Central Hospital", "Dermatology"): ["Dr. Lopez"],
            ("North Hospital", "Pediatrics"): ["Dr. Ruiz"],
            ("North Hospital", "Traumatology"): ["Dr. Fernandez", "Dr. Ortega"],
        }
        return mapping.get((hospital, specialty), [])

    def get_appointment_slots(self, hospital: str, specialty: str, doctor: str) -> list[str]:
        """Return available appointment slots."""
        mapping = {
            ("Central Hospital", "Cardiology", "Dr. Garcia"): [
                "2024-05-01 10:00",
                "2024-05-01 12:00",
            ],
            ("Central Hospital", "Cardiology", "Dr. Perez"): [
                "2024-05-02 09:30",
            ],
            ("North Hospital", "Pediatrics", "Dr. Ruiz"): [
                "2024-05-03 15:00",
                "2024-05-04 11:00",
            ],
        }
        return mapping.get((hospital, specialty, doctor), [])