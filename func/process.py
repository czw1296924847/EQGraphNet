"""
Functions for processing and calculating data
"""
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import h5py
import os
import os.path as osp
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler, MinMaxScaler


class Chunk(Dataset):
    def __init__(self, num, train, num_train, idx, root, name):
        super(Chunk, self).__init__()
        self.num = num
        self.root = root
        self.save_address = osp.join(root, str(num))
        self.name = name
        self.df, self.dtfl = self.get_merge()
        self.data, self.index = self.get_sample()
        self.df = self.df.iloc[self.index, :]
        self.num_train = num_train
        self.length = self.data.shape[2]
        self.train = train
        self.idx = idx
        self.get_train_or_test()

    def get_train_or_test(self):
        self.data = self.data[self.idx, :, :]
        self.index = self.index[self.idx]
        self.df = self.df.iloc[self.idx, :]
        return None

    def __len__(self):
        return self.data.shape[0]

    def __getitem__(self, idx):
        data, index = self.data[idx, :, :], self.index[idx]
        return data, index

    def get_merge(self):
        csv_address = osp.join(self.root, self.name + ".csv")
        file_address = osp.join(self.root, self.name + ".hdf5")
        df = pd.read_csv(csv_address)
        dtfl = h5py.File(file_address, 'r')
        return df, dtfl

    def get_sample(self):
        if not osp.exists(self.save_address):
            os.makedirs(self.save_address)
        data_address = osp.join(self.save_address, "data.pt")
        index_address = osp.join(self.save_address, "index.pt")
        if osp.exists(data_address) & osp.exists(index_address):
            data = torch.load(data_address)
            index = torch.load(index_address)
        else:
            trace_name = self.df.loc[:, "trace_name"].values.reshape(-1)
            index = np.random.choice(trace_name.shape[0], self.num, replace=False).tolist()

            ev_list = self.df['trace_name'].to_list()
            data = np.zeros(shape=(self.num, 3, 6000))
            for c, i in enumerate(index):
                ev_one = ev_list[i]
                dataset_one = self.dtfl.get('data/' + str(ev_one))
                data_one = np.array(dataset_one)
                data_one = np.expand_dims(data_one.T, axis=0)
                data[c, :, :] = data_one

            data = torch.from_numpy(data).float()
            index = torch.FloatTensor(index).int()

            torch.save(data, data_address)
            torch.save(index, index_address)
        if self.num != data.shape[0]:
            raise ValueError("data.shape[0] is not equal to num. Please delete the file saved before and run again!")
        return data, index


def get_train_or_test_idx(num, num_train):
    idx_all = np.arange(num)
    idx_train = np.random.choice(num, num_train, replace=False)
    idx_test = list(set(idx_all) - set(idx_train))
    return idx_train, idx_test


def be_tensor(x):
    if type(x) == np.ndarray:
        return torch.from_numpy(x)
    elif torch.is_tensor(x):
        return x
    else:
        raise TypeError("x must be tensor or ndarray, but gut {}".format(type(x)))


class SelfData(Dataset):
    def __init__(self, data, label, *args):
        super(SelfData, self).__init__()
        self.data = be_tensor(data)
        self.label = be_tensor(label)
        self.args = args
        self.data_else = self.get_data_else()

    def get_data_else(self):
        num = len(self.args)
        if num != 0:
            data_else = []
            for i in range(num):
                data_else_one = self.args[i]
                data_else.append(data_else_one)
        else:
            data_else = None
        return data_else

    def __len__(self):
        return self.data.shape[0]

    def __getitem__(self, item):
        if self.data.dim() == 3:
            data_one = self.data[item, :, :]
        elif self.data.dim() == 4:
            data_one = self.data[item, :, :, :]
        else:
            raise ValueError("data.dim() must be 3 or 4, but got {}".format(self.data.dim()))
        if self.label.dim() == 1:
            label_one = self.label[item]
        elif self.label.dim() == 2:
            label_one = self.label[item, :]
        else:
            raise ValueError("label.dim() must be 1 or 2, but got {}".format(self.label.dim()))
        return_all = [data_one, label_one]
        data_else_one = []
        if self.data_else is not None:
            num = len(self.data_else)
            for i in range(num):
                x = self.data_else[i]
                if torch.is_tensor(x):
                    if x.dim() == 2:
                        x_one = x[item, :]
                    elif x.dim() == 1:
                        x_one = x[item]
                    else:
                        raise ValueError("data_else dim() must be 1 or 2, but got {}".format(x.dim()))
                elif type(x) is np.ndarray:
                    if x.ndim == 2:
                        x_one = x[item, :]
                    elif x.ndim == 1:
                        x_one = x[item]
                    else:
                        raise ValueError("data_else ndim must be 1 or 2, but got {}".format(x.ndim))
                else:
                    raise TypeError("Unknown type of x, must be tensor or ndarray!")
                data_else_one.append(x_one)
        return_all = return_all + data_else_one
        return_all.append(item)
        return_all = tuple(return_all)
        return return_all


def ts_un(n, k):
    adm = np.zeros(shape=(n, n))
    if k < 1:
        raise ValueError("k must be greater than or equal to 1")
    else:
        for i in range(n):
            if i < (n - k):
                for k_one in range(1, k + 1):
                    adm[i, i + k_one] = 1.
            else:
                for k_one in range(1, k + 1):
                    if (k_one + i) >= n:
                        mod = (k_one + i) % n
                        adm[i, mod] = 1.
                    else:
                        adm[i, i + k_one] = 1.
    adm = (adm.T + adm) / 2
    # adm = adm * 0.5
    return adm


def prep_tran(prep_style, train, *args):
    if prep_style == "sta":
        prep = StandardScaler()
    elif prep_style == "min":
        prep = MinMaxScaler()
    else:
        raise TypeError("Unknown Type of prep_style!")
    prep.fit(train)
    train_prep = prep.transform(train)
    train_prep = train_prep.reshape(train.shape)
    num, prep_other = len(args), []
    for i in range(num):
        one = args[i]
        one_tran = prep.transform(one)
        one_tran = one_tran.reshape(one.shape)
        prep_other.append(one_tran)
    if num == 1:
        prep_other = prep_other[0]
    elif num == 0:
        return prep, train_prep
    else:
        prep_other = tuple(prep_other)
    return prep, train_prep, prep_other


def prep_inv(prep, *args):
    num = len(args)
    if num == 0:
        raise ValueError("Please input data for inverse-normalization!")
    inv = []
    for i in range(num):
        one = args[i]
        one_inv = prep.inverse_transform(one)
        one_inv = one_inv.reshape(one.shape)
        inv.append(one_inv)
    if num == 1:
        inv = inv[0]
    else:
        inv = tuple(inv)
    return inv


def tran_adm_to_edge_index(adm):
    u, v = np.nonzero(adm)
    num_edges = u.shape[0]
    edge_index = np.vstack([u.reshape(1, -1), v.reshape(1, -1)])
    edge_weight = np.zeros(shape=u.shape)
    for i in range(num_edges):
        edge_weight_one = adm[u[i], v[i]]
        edge_weight[i] = edge_weight_one
    edge_index = torch.from_numpy(edge_index).long()
    edge_weight = torch.from_numpy(edge_weight).float()
    return edge_index, edge_weight


def remain_sm_scale(data, df, label, scale):
    smt = df.source_magnitude_type.values.reshape(-1)
    idx = np.argwhere(smt == scale).reshape(-1)
    data = data[idx, :, :]
    label = label[idx]
    df = df.iloc[idx, :]
    return data, label, df