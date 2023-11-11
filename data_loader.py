import os
import cv2
import torch
import numpy as np
from torch.utils.data import Dataset, DataLoader, BatchSampler
from sklearn.model_selection import train_test_split

class KTHDataset(Dataset):
    def __init__(self, video_list, transform=None, frame_skip=3, use_diff=True):
        self.video_list = video_list
        self.transform = transform
        self.frame_skip = frame_skip
        self.use_diff = use_diff
        self.preprocessed_frames = []
        self.frame_counts = {}

        self.preprocess_and_store_frame_counts()

    def __len__(self):
        return len(self.video_list)

    def __getitem__(self, idx):
        frames = self.preprocessed_frames[idx]
        label = self.video_list[idx][1]

        # Apply transformations if any
        if self.transform:
            frames = self.transform(frames)

        frames_tensor = torch.from_numpy(np.array(frames)).float().unsqueeze(1)
        label_tensor = torch.tensor(label, dtype=torch.long)
        return frames_tensor, label_tensor
    
    def preprocess_and_store_frame_counts(self):
        for idx, (path, _) in enumerate(self.video_list):
            cap = cv2.VideoCapture(path)
            frames = []
            frame_count = 0
            prev_frame = None

            while(cap.isOpened()):
                ret, frame = cap.read()
                if ret:
                    if frame_count % self.frame_skip == 0:
                        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        if self.use_diff:
                            if prev_frame is not None:
                                diff_frame = cv2.absdiff(gray_frame, prev_frame) > 60
                                frames.append(diff_frame)
                            prev_frame = gray_frame
                        else:
                            frames.append(gray_frame)
                    frame_count += 1
                else:
                    break
            cap.release()

            # Calculate the sum of pixel values for each frame
            frame_sums = np.array([frame.sum() for frame in frames])

            # Calculate the mean of these sums
            mean_frame_sum = frame_sums.mean()

            # Filter out frames and count them
            processed_frames = [frame for frame, frame_sum in zip(frames, frame_sums) if frame_sum >= mean_frame_sum]
            filtered_frame_count = len(processed_frames)
            
            self.preprocessed_frames.append(processed_frames)
            self.frame_counts[idx] = filtered_frame_count

def get_loaders(batch_size=4):
    # Load video paths and labels
    actions = ['walking', 'jogging', 'running', 'boxing', 'handwaving', 'handclapping']
    video_files = []
    labels = []

    for i, action in enumerate(actions):
        folder = os.path.join("data/KTH_Dataset", action)
        for filename in os.listdir(folder):
            if filename.endswith(".avi"):
                path = os.path.join(folder, filename)
                video_files.append(path)
                labels.append(i)

    # Split data into training, validation, and test sets
    videos_train, videos_test, labels_train, labels_test = train_test_split(video_files, labels, test_size=0.2, random_state=42, stratify=labels)
    videos_train, videos_val, labels_train, labels_val = train_test_split(videos_train, labels_train, test_size=0.25, random_state=42, stratify=labels_train)

    train_data = [(v, l) for v, l in zip(videos_train, labels_train)]
    val_data = [(v, l) for v, l in zip(videos_val, labels_val)]
    test_data = [(v, l) for v, l in zip(videos_test, labels_test)]

    train_dataset = KTHDataset(train_data, use_diff=True)
    val_dataset = KTHDataset(val_data, use_diff=True)
    test_dataset = KTHDataset(test_data, use_diff=True)

    train_sampler = BucketBatchSampler(train_dataset, batch_size)
    val_sampler = BucketBatchSampler(val_dataset, batch_size)
    test_sampler = BucketBatchSampler(test_dataset, batch_size)

    train_loader = DataLoader(train_dataset, batch_sampler=train_sampler)
    val_loader = DataLoader(val_dataset, batch_sampler=val_sampler)
    test_loader = DataLoader(test_dataset, batch_sampler=test_sampler)

    return train_loader, val_loader, test_loader

class BucketBatchSampler(BatchSampler):
    def __init__(self, dataset, batch_size):
        self.dataset = dataset
        self.batch_size = batch_size
        self.buckets = self.create_buckets()

    def create_buckets(self):
        # Group data by stored frame counts
        buckets = {}
        for idx, frame_count in self.dataset.frame_counts.items():
            bucket_key = frame_count // self.batch_size
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(idx)

        return buckets

    def __iter__(self):
        for bucket_key in self.buckets:
            bucket_indices = self.buckets[bucket_key]
            for i in range(0, len(bucket_indices), self.batch_size):
                yield bucket_indices[i:i + self.batch_size]

    def __len__(self):
        return sum(len(indices) // self.batch_size for indices in self.buckets.values())
