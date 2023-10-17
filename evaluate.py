from data_loader import get_loaders

import torch
import torch.nn as nn
import snntorch as snn
from snntorch import surrogate
from snntorch import utils
from tqdm import tqdm

import numpy as np

import torch.optim as optim
from sklearn.metrics import accuracy_score

from architectures import RecurrentSNN

from config import num_steps, batch_size, num_classes, beta, spike_grad
if spike_grad == "fast_sigmoid":
    spike_grad = surrogate.fast_sigmoid()

train_loader, val_loader, test_loader = get_loaders(batch_size)

net = RecurrentSNN(beta, spike_grad)

# Loss and optimizer
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(net.parameters(), lr=0.005)

# Number of epochs
num_epochs = 10
train_loader_elements = len(train_loader.dataset)
best_val_accuracy = 0.0

for epoch in range(num_epochs):
    
    net.train()
    epoch_train_loss = 0

    with tqdm(total=train_loader_elements, desc=f"Epoch {epoch+1}/{num_epochs}", postfix={'train_loss':0.0, 'val_acc':0.0}) as pbar:

        # Training loop
        for batch_idx, (data, target) in enumerate(train_loader):
            optimizer.zero_grad()
            
            # Reset/initialize hidden states for all neurons
            utils.reset(net)

            data = data.permute(1, 0, 2, 3, 4)  # Permute for time steps

            spike = net(data)
            
            loss = criterion(spike, target)
            loss.backward()
            optimizer.step()

            epoch_train_loss += loss.item()

            pbar.update(data.size(1))
        
        # Validation loop
        net.eval()
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for batch_idx, (data, target) in enumerate(val_loader):
                # Reset/initialize hidden states for all neurons
                utils.reset(net)
                
                data = data.permute(1, 0, 2, 3, 4)  # Permute for time steps

                spike = net(data)
                
                all_preds.append(spike.argmax(dim=1).cpu().numpy())
                all_labels.append(target.cpu().numpy())
                
        all_preds = np.concatenate(all_preds)
        all_labels = np.concatenate(all_labels)
        val_accuracy = accuracy_score(all_preds, all_labels)
        
        print(f"Epoch [{epoch+1}/{num_epochs}], Train Loss: {epoch_train_loss/len(train_loader):.4f}, Val Accuracy: {val_accuracy*100:.2f}%")

        if val_accuracy > best_val_accuracy:
            best_val_accuracy = val_accuracy
            torch.save(net.state_dict(), f'{best_val_accuracy*100:.2f}_snn.pth')
            print(f"Saved best model with validation accuracy: {best_val_accuracy*100:.2f}%")

