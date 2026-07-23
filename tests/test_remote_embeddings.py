import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from agentic.document_retrieval.remote_embeddings import RemoteEmbeddingsClient

class TestRemoteEmbeddingsClient(unittest.TestCase):

    @patch("requests.post")
    def test_generate_embedding_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        dummy_vec = [0.1] * 384
        mock_resp.json.return_value = {"embedding": dummy_vec, "shape": [384]}
        mock_post.return_value = mock_resp

        client = RemoteEmbeddingsClient(api_url="https://mock-colab.ngrok-free.app")
        vec = client.generate_embedding("Open HealthSphere document")

        self.assertIsNotNone(vec)
        self.setIsInstance(vec, np.ndarray) if hasattr(self, 'setIsInstance') else self.assertTrue(isinstance(vec, np.ndarray))
        self.assertEqual(vec.shape, (384,))
        self.assertEqual(vec.dtype, np.float32)
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_generate_embeddings_batch_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        dummy_vecs = [[0.1] * 384, [0.2] * 384]
        mock_resp.json.return_value = {"embeddings": dummy_vecs, "count": 2}
        mock_post.return_value = mock_resp

        client = RemoteEmbeddingsClient(api_url="https://mock-colab.ngrok-free.app")
        vecs = client.generate_embeddings_batch(["HealthSphere", "Money Mentor"])

        self.assertEqual(len(vecs), 2)
        self.assertTrue(isinstance(vecs[0], np.ndarray))
        self.assertTrue(isinstance(vecs[1], np.ndarray))
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_remote_embedding_offline_fallback(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        client = RemoteEmbeddingsClient(api_url="https://offline-colab.ngrok-free.app")
        vec = client.generate_embedding("test query")
        self.assertIsNone(vec)

if __name__ == "__main__":
    unittest.main()
