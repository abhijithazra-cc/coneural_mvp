from abc import ABC, abstractmethod

class OCRProvider(ABC):

    @abstractmethod
    def extract(self, image_bytes: bytes) -> str:
        """Extract all text/data from image bytes"""
        pass
