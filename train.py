# -*- coding: utf-8 -*-
import os
import re
import ast
import torch.nn.functional as F
import torch.utils.data as torch_data
from torch.utils.data import Dataset, DataLoader
import torchmetrics
import time
from model import *
import sys
import fm
from evo import Evo
import argparse

sys.path.append(os.path.abspath(''))

#  If you have any internet error please try this code with your proxy setting.
#  os.environ["http_proxy"] = "http://...:8888"
#  os.environ["https_proxy"] = "http://...:8888"


def sigmoid(x, k=0.05):
    return 1 / (1 + np.exp(-k * x))


def standardization(data):
    mu = np.mean(data, axis=0)
    sigma = np.std(data, axis=0)
    return (data - mu) / sigma


def convert_to_rna_sequence_rna_fm(data):
    rna_to_num = {'A': 1, 'C': 2, 'G': 3, 'U': 4}

    numbers = [rna_to_num.get(base, -1) for base in data.upper()]

    return numbers


def convert_to_rna_sequence_evo(data):
    mapping = {1: 'A', 2: 'C', 3: 'G', 4: 'U'}

    rna_sequence = ''.join([mapping[number] for number in data])

    return rna_sequence


def read_data_rna_fm(file_path, EmbbingModel, batch_converter, device):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    rnas = []
    input_seqs = []
    true_seqs = []
    bd_scores = []

    for line in lines:
        words = line.split()
        b = words[-1]

        rna_one_hot = convert_to_rna_sequence_rna_fm(b)

        values_list = list(rna_one_hot)

        values_list.insert(0, 0)

        input_seq = values_list[:-1]
        true_seq = values_list[1:]
        decimal_part = float(words[0])
        decimal_part = (sigmoid(decimal_part, 0.05) - 0.5) * 2.0

        seq = ("undefined", b)
        seq_unused = ('UNUSE', 'ACGU')
        all_rna = []
        all_rna.append(seq)
        all_rna.append(seq_unused)

        rna_fm = rna_seq_embbding(all_rna, batch_converter, EmbbingModel, device)
        rna_fm = rna_fm[1:-1, :]
        rna_fm = rna_fm.cpu().numpy()

        rna_fm = rna_fm.reshape(-1)
        rna_fm = standardization(rna_fm)

        rnas.append(rna_fm)
        input_seqs.append(input_seq)
        true_seqs.append(true_seq)
        bd_scores.append(decimal_part)
    return rnas, input_seqs, true_seqs, bd_scores


def get_data_rna_fm(file_path, is_batch, device):
    EmbbingModel, batch_converter = get_rna_fm_model(device)

    rnas, input_seqs, true_seqs, bd_scores = read_data_rna_fm(file_path, EmbbingModel, batch_converter, device)

    if is_batch:
        rnas1 = torch.tensor(rnas)
        input_seqs1 = torch.tensor(np.asarray(input_seqs))
        true_seqs1 = torch.tensor(np.asarray(true_seqs))
        bd_scores1 = torch.tensor(np.asarray(bd_scores))
    else:
        rnas1 = torch.tensor(rnas).to(device)
        input_seqs1 = torch.tensor(np.asarray(input_seqs)).to(device)
        true_seqs1 = torch.tensor(np.asarray(true_seqs)).to(device)
        bd_scores1 = torch.tensor(np.asarray(bd_scores)).to(device)

    return rnas1, input_seqs1, true_seqs1, bd_scores1


def read_data_evo(file_path, model, tokenizer, device):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    rnas = []
    input_seqs = []
    true_seqs = []
    bd_scores = []

    for line in lines:
        words = line.split()
        b = words[-1]

        rna_one_hot = convert_to_rna_sequence_rna_fm(b)

        values_list = list(rna_one_hot)

        values_list.insert(0, 0)

        input_seq = values_list[:-1]
        true_seq = values_list[1:]

        decimal_part = float(words[0])
        decimal_part = (sigmoid(decimal_part, 0.05) - 0.5) * 2.0

        sequence = b

        input_ids = torch.tensor(
            tokenizer.tokenize(sequence),
            dtype=torch.int,
        ).to(device).unsqueeze(0)

        with torch.no_grad():
            logits, _ = model(input_ids)

        logits = logits.detach()
        logits = logits.float()
        cpu_logits = logits.cpu()

        rna_embedding = cpu_logits.numpy()

        rna_embedding = rna_embedding.reshape(-1)
        rna_embedding = standardization(rna_embedding)

        rnas.append(rna_embedding)
        input_seqs.append(input_seq)
        true_seqs.append(true_seq)
        bd_scores.append(decimal_part)
    return rnas, input_seqs, true_seqs, bd_scores


def get_data_evo(file_path, is_batch, device):
    evo_model = Evo('evo-1-8k-base')
    model, tokenizer = evo_model.model, evo_model.tokenizer
    model.to(device)
    model.eval()
    rnas, input_seqs, true_seqs, bd_scores = read_data_evo(file_path, model, tokenizer, device)

    if is_batch:
        rnas1 = torch.tensor(rnas)
        input_seqs1 = torch.tensor(np.asarray(input_seqs))
        true_seqs1 = torch.tensor(np.asarray(true_seqs))
        bd_scores1 = torch.tensor(np.asarray(bd_scores))
    else:
        rnas1 = torch.tensor(rnas).to(device)
        input_seqs1 = torch.tensor(np.asarray(input_seqs)).to(device)
        true_seqs1 = torch.tensor(np.asarray(true_seqs)).to(device)
        bd_scores1 = torch.tensor(np.asarray(bd_scores)).to(device)

    return rnas1, input_seqs1, true_seqs1, bd_scores1


def get_rna_fm_model(device):
    torch.cuda.empty_cache()

    EmbbingModel, alphabet = fm.pretrained.rna_fm_t12()
    batch_converter = alphabet.get_batch_converter()
    EmbbingModel.to(device)
    EmbbingModel.eval()

    return EmbbingModel, batch_converter


def rna_seq_embbding(OriginSeq, batch_converter, EmbeddingModel, device):
    EmbeddingModel = EmbeddingModel.to(device)
    batch_labels, batch_strs, batch_tokens = batch_converter(OriginSeq)
    batch_tokens = batch_tokens.to(device)

    tmp = []

    with torch.no_grad():
        results = EmbeddingModel(batch_tokens, repr_layers=[12])
    token_embeddings = results["representations"][12][0]

    return token_embeddings



def train_guidance_LLM_rna_fm(train_file, test_file, batch_size, model_name, device):
    tr_feats, tr_input_seqs, tr_true_seqs, tr_bd_scores = get_data_rna_fm(train_file, is_batch=True, device=device)
    te_feats, te_input_seqs, te_true_seqs, te_bd_scores = get_data_rna_fm(test_file, is_batch=True, device=device)

    train_data = torch_data.TensorDataset(tr_feats, tr_input_seqs, tr_true_seqs, tr_bd_scores)
    test_data = torch_data.TensorDataset(te_feats, te_input_seqs, te_true_seqs, te_bd_scores)

    train_loader = DataLoader(dataset=train_data,
                              batch_size=batch_size,
                              shuffle=True,
                              num_workers=0,
                              pin_memory=True,
                              drop_last=False)
    test_loader = DataLoader(dataset=test_data,
                             batch_size=batch_size,
                             shuffle=True,
                             num_workers=0,
                             pin_memory=True,
                             drop_last=False)

    model = FullModel_guidance_RNA_FM(input_dim=12800,
                                      model_dim=128,
                                      tgt_size=5,
                                      n_declayers=2,
                                      d_ff=128,
                                      d_k_v=64,
                                      n_heads=2,
                                      dropout=0.05)

    model = model.to(device)

    loss_func1 = nn.MSELoss()
    loss_func2 = nn.CrossEntropyLoss(ignore_index=0)

    w = 0.50

    fw = open('log/' + model_name + '_training_log.txt', 'w')
    for epoch in range(250):
        start_t = time.time()
        loss1_value = 0.0
        loss2_value = 0.0
        acc2 = 0.0
        b_num = 0.0

        # optimizer = torch.optim.Adam(model.parameters(), lr=(250.0 - epoch) * 0.00001)
        optimizer = torch.optim.Adam(model.parameters(), lr=max((250.0 - epoch) * 0.00001, 0.0001))
        # optimizer = torch.optim.Adam(model.parameters(), lr=0.0006)

        model.train()
        for i, data in enumerate(train_loader):
            inputs, input_seqs, true_seqs, labels = data
            inputs = inputs.to(device)
            input_seqs = input_seqs.to(device)
            true_seqs = true_seqs.to(device)
            labels = labels.to(device)

            labels = labels.float().view(-1, 1)
            bind_socres, pred_seqs = model(inputs, input_seqs)

            pred_seqs = torch.softmax(pred_seqs, -1)
            true_seqs = true_seqs.view(-1)
            pred_seqs = pred_seqs.view(true_seqs.shape[0], 5)

            loss1 = loss_func1(bind_socres, labels)
            loss2 = loss_func2(pred_seqs, true_seqs)
            pred_seqs = torch.argmax(pred_seqs, -1)

            acc2 += torchmetrics.functional.accuracy(pred_seqs,
                                                     true_seqs,
                                                     task="multiclass",
                                                     num_classes=5,
                                                     ignore_index=0,
                                                     average="micro")

            loss = w * loss1 + (1.0 - w) * loss2

            loss1_value += loss1.item()
            loss2_value += loss2.item()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            b_num += 1.

        test_loss1_value = 0.0
        test_loss2_value = 0.0

        te_acc2 = 0.0
        test_b_num = 0.

        model.eval()
        for i, data in enumerate(test_loader):
            inputs, input_seqs, true_seqs, labels = data
            inputs = inputs.to(device)
            input_seqs = input_seqs.to(device)
            true_seqs = true_seqs.to(device)
            labels = labels.to(device)

            bind_socres, pred_seqs = model(inputs, input_seqs)
            pred_seqs = torch.softmax(pred_seqs, -1)
            labels = labels.float().view(-1, 1)

            true_seqs = true_seqs.view(-1)
            pred_seqs = pred_seqs.view(true_seqs.shape[0], 5)

            loss1 = loss_func1(bind_socres, labels)
            loss2 = loss_func2(pred_seqs, true_seqs)

            pred_seqs = torch.argmax(pred_seqs, -1)
            te_acc2 += torchmetrics.functional.accuracy(pred_seqs,
                                                        true_seqs,
                                                        task="multiclass",
                                                        num_classes=5,
                                                        ignore_index=0,
                                                        average="micro")

            test_loss1_value += loss1.item()
            test_loss2_value += loss2.item()
            test_b_num += 1.
        end_t = time.time()
        fw.write('{:4d}\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}\n'.format(epoch,
                                                                  loss1_value / b_num,
                                                                  loss2_value / b_num,
                                                                  test_loss1_value / test_b_num,
                                                                  test_loss2_value / test_b_num,
                                                                  acc2 / b_num,
                                                                  te_acc2 / test_b_num), )
        print('Epoch:', '%04d' % (epoch + 1),
              '| tr_loss1 =', '{:.4f}'.format(loss1_value / b_num),
              '| tr_loss2 =', '{:.4f}'.format(loss2_value / b_num),
              '| tr_acc =', '{:.2f}'.format(acc2 / b_num),
              '| te_loss1 =', '{:.4f}'.format(test_loss1_value / test_b_num),
              '| te_loss2 =', '{:.4f}'.format(test_loss2_value / test_b_num),
              '| te_acc =', '{:.2f}'.format(te_acc2 / test_b_num),
              '| time =', '{:.2f}'.format(end_t - start_t)
              )
    torch.save(model, 'model/' + model_name)


def train_guidance_LLM_Evo(train_file, test_file, batch_size, model_name, device):
    tr_feats, tr_input_seqs, tr_true_seqs, tr_bd_scores = get_data_evo(train_file, is_batch=True, device=device)
    te_feats, te_input_seqs, te_true_seqs, te_bd_scores = get_data_evo(test_file, is_batch=True, device=device)

    train_data = torch_data.TensorDataset(tr_feats, tr_input_seqs, tr_true_seqs, tr_bd_scores)
    test_data = torch_data.TensorDataset(te_feats, te_input_seqs, te_true_seqs, te_bd_scores)

    train_loader = DataLoader(dataset=train_data,
                              batch_size=batch_size,
                              shuffle=True,
                              num_workers=0,
                              pin_memory=True,
                              drop_last=False)
    test_loader = DataLoader(dataset=test_data,
                             batch_size=batch_size,
                             shuffle=True,
                             num_workers=0,
                             pin_memory=True,
                             drop_last=False)

    model = FullModel_guidance_Evo(input_dim=10240,
                                   model_dim=128,
                                   tgt_size=5,
                                   n_declayers=2,
                                   d_ff=128,
                                   d_k_v=64,
                                   n_heads=2,
                                   dropout=0.05)

    model = model.to(device)

    loss_func1 = nn.MSELoss()
    loss_func2 = nn.CrossEntropyLoss(ignore_index=0)

    w = 0.50

    fw = open('log/' + model_name + '_training_log.txt', 'w')
    for epoch in range(250):
        start_t = time.time()
        loss1_value = 0.0
        loss2_value = 0.0
        acc2 = 0.0
        b_num = 0.0

        # optimizer = torch.optim.Adam(model.parameters(), lr=(250.0 - epoch) * 0.00001)
        optimizer = torch.optim.Adam(model.parameters(), lr=max((250.0 - epoch) * 0.00001, 0.0001))
        # optimizer = torch.optim.Adam(model.parameters(), lr=0.0006)

        model.train()
        for i, data in enumerate(train_loader):
            inputs, input_seqs, true_seqs, labels = data
            inputs = inputs.to(device)
            input_seqs = input_seqs.to(device)
            true_seqs = true_seqs.to(device)
            labels = labels.to(device)

            labels = labels.float().view(-1, 1)
            bind_socres, pred_seqs = model(inputs, input_seqs)

            pred_seqs = torch.softmax(pred_seqs, -1)
            true_seqs = true_seqs.view(-1)
            pred_seqs = pred_seqs.view(true_seqs.shape[0], 5)

            loss1 = loss_func1(bind_socres, labels)
            loss2 = loss_func2(pred_seqs, true_seqs)
            pred_seqs = torch.argmax(pred_seqs, -1)

            acc2 += torchmetrics.functional.accuracy(pred_seqs,
                                                     true_seqs,
                                                     task="multiclass",
                                                     num_classes=5,
                                                     ignore_index=0,
                                                     average="micro")

            loss = w * loss1 + (1.0 - w) * loss2

            loss1_value += loss1.item()
            loss2_value += loss2.item()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            b_num += 1.

        test_loss1_value = 0.0
        test_loss2_value = 0.0

        te_acc2 = 0.0
        test_b_num = 0.

        model.eval()
        for i, data in enumerate(test_loader):
            inputs, input_seqs, true_seqs, labels = data
            inputs = inputs.to(device)
            input_seqs = input_seqs.to(device)
            true_seqs = true_seqs.to(device)
            labels = labels.to(device)

            bind_socres, pred_seqs = model(inputs, input_seqs)
            pred_seqs = torch.softmax(pred_seqs, -1)
            labels = labels.float().view(-1, 1)

            true_seqs = true_seqs.view(-1)
            pred_seqs = pred_seqs.view(true_seqs.shape[0], 5)

            loss1 = loss_func1(bind_socres, labels)
            loss2 = loss_func2(pred_seqs, true_seqs)

            pred_seqs = torch.argmax(pred_seqs, -1)
            te_acc2 += torchmetrics.functional.accuracy(pred_seqs,
                                                        true_seqs,
                                                        task="multiclass",
                                                        num_classes=5,
                                                        ignore_index=0,
                                                        average="micro")

            test_loss1_value += loss1.item()
            test_loss2_value += loss2.item()
            test_b_num += 1.
        end_t = time.time()
        fw.write('{:4d}\t{:.4f}\t{:.4f}\t{:.4f}\t{:.4f}\n'.format(epoch,
                                                                  loss1_value / b_num,
                                                                  loss2_value / b_num,
                                                                  test_loss1_value / test_b_num,
                                                                  test_loss2_value / test_b_num,
                                                                  acc2 / b_num,
                                                                  te_acc2 / test_b_num), )
        print('Epoch:', '%04d' % (epoch + 1),
              '| tr_loss1 =', '{:.4f}'.format(loss1_value / b_num),
              '| tr_loss2 =', '{:.4f}'.format(loss2_value / b_num),
              '| tr_acc =', '{:.2f}'.format(acc2 / b_num),
              '| te_loss1 =', '{:.4f}'.format(test_loss1_value / test_b_num),
              '| te_loss2 =', '{:.4f}'.format(test_loss2_value / test_b_num),
              '| te_acc =', '{:.2f}'.format(te_acc2 / test_b_num),
              '| time =', '{:.2f}'.format(end_t - start_t)
              )
    torch.save(model, 'model/' + model_name)



def main():
    parser = argparse.ArgumentParser(description="Choose which function to run.")
    parser.add_argument('function', choices=['1', '2', '3'], help="Function to run")
    parser.add_argument('--cuda', type=str, default="0", help="CUDA device ID (e.g., '0', '1', '2')")
    parser.add_argument('--train_file', type=str)
    parser.add_argument('--test_file', type=str)
    parser.add_argument('--model_name', type=str)
    parser.add_argument('--batch_size', type=int, default="1000")

    args = parser.parse_args()

    # os.environ["CUDA_VISIBLE_DEVICES"] = f'{args.cuda}'

    CUDA = args.cuda
    train_file = args.train_file
    test_file = args.test_file
    batch_size = args.batch_size
    model_name = args.model_name

    os.environ["CUDA_VISIBLE_DEVICES"] = f'{CUDA}'

    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    if args.function == '1':
        train_guidance_LLM_rna_fm(train_file, test_file, batch_size, model_name, device)
    elif args.function == '2':
        train_guidance_LLM_Evo(train_file, test_file, batch_size, model_name, device)


if __name__ == '__main__':
    main()
