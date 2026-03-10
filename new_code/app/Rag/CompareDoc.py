from datasketch import MinHash
import pickle

class CompareDoc:
    def __init__(self, num_perm: int = 128, k: int = 3):
        """
        Compare document similarity using MinHash signatures.
        
        Args:
            num_perm (int): Number of permutations for MinHash.
            k (int): Shingle size.
        """
        self.num_perm = num_perm
        self.k = k

    # --------------------------
    # Shingle Generator
    # --------------------------
    def get_sentence_shingles(self, sentence: str):
        """
        Convert text into k-length character shingles.

        Returns:
            set: Unique shingles.
        """
        sentence = sentence.lower()
        shingles = set()

        for i in range(len(sentence) - self.k + 1):
            shingles.add(sentence[i:i + self.k])

        return shingles

    # --------------------------
    # Create MinHash from text
    # --------------------------
    def create_minhash(self, text: str) -> MinHash:
        """
        Build a MinHash signature for a sentence.

        Returns:
            MinHash object
        """
        shingles = self.get_sentence_shingles(text)
        m = MinHash(num_perm=self.num_perm)

        for s in shingles:
            m.update(s.encode("utf8"))

        return m

    # --------------------------
    # Calculate similarity from raw text
    # --------------------------
    def from_text(self, text1: str, text2: str) -> float:
        """
        Calculate similarity from raw sentence inputs.

        Returns:
            float: similarity score 0–1
        """
        m1 = self.create_minhash(text1)
        m2 = self.create_minhash(text2)

        return m1.jaccard(m2)

    # --------------------------
    # Direct similarity from existing MinHash signatures
    # --------------------------
    @staticmethod
    def calculate_similarity(mh1: MinHash, mh2: MinHash) -> float:
        """
        Calculate similarity between two precomputed MinHash signatures.
        Useful when signatures are stored in DB.

        Returns:
            float
        """
        return mh1.jaccard(mh2)

    # --------------------------
    # Serialization Helpers
    # --------------------------
    @staticmethod
    def serialize_minhash(mh: MinHash) -> bytes:
        return pickle.dumps(mh)

    @staticmethod
    def deserialize_minhash(data: bytes) -> MinHash:
        return pickle.loads(data)
