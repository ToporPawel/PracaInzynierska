import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import Times as t

plt.close("all")
MSE_NAMES = {0: "MSE-NS-3", 1: "MSE-AM", 2: "MSE-MS"}


def calculate_p_coll_mse(csv_name, notes=""):
    results = pd.read_csv("results_p_coll.csv", delimiter=",")
    results_dict = results.iloc[0:3, 0:10].to_dict()
    new_results = pd.read_csv(csv_name, delimiter=",").T
    new_results = {
        str(int(pair["N_OF_STATIONS"])): pair["P_COLL"]
        for pair in new_results.to_dict().values()
    }
    new_results["Name"] = "DCF-SimPy"
    new_results["Notes"] = notes
    for i in range(3):
        mse = 0
        for key in results_dict.keys():
            mse += pow(results_dict[key][i] - new_results[key], 2)
        mse = mse / len(results_dict.keys())
        new_results[MSE_NAMES[i]] = "{:.2E}".format(mse)
    results = results.append(new_results, ignore_index=True)
    results.to_csv("results_p_coll.csv", index=False)
    ax = results.iloc[[0, 1, 2, -1], 0:10].T.plot(style="--o")
    ax.set_xlabel("Number of stations")
    ax.set_ylabel("Collision probability")
    x_ticks = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ax.set_xticks(range(len(x_ticks)))
    ax.set_xticklabels(x_ticks)
    ax.legend(results.iloc[[0, 1, 2, -1], 10].tolist())
    ax.text(
        0.58,
        0.13,
        "MSE for DCF-SimPy vs:\nns-3: {}\nAnalitical model: {}\nMatlab simulation: {}".format(
            *results.iloc[-1, 11:14].tolist()
        ),
        bbox={"facecolor": "none", "pad": 10, "edgecolor": "grey"},
        ha="left",
        va="center",
        transform=ax.transAxes,
    )


def calculate_thr_mse(csv_name, notes=""):
    results = pd.read_csv("results_thr.csv", delimiter=",")
    results_dict = results.iloc[0:2, 0:10].to_dict()
    new_results = pd.read_csv(csv_name, delimiter=",").T
    new_results = {
        str(int(pair["N_OF_STATIONS"])): pair["THR"]
        for pair in new_results.to_dict().values()
    }
    new_results["Name"] = "DCF-SimPy"
    new_results["Notes"] = notes
    for i in range(2):
        mse = 0
        for key in results_dict.keys():
            mse += pow(results_dict[key][i] - new_results[key], 2)
        mse = mse / len(results_dict.keys())
        new_results[MSE_NAMES[i]] = "{:.2E}".format(mse)
    results = results.append(new_results, ignore_index=True)
    results.to_csv("results_thr.csv", index=False)
    # plt.figure()
    ax = results.iloc[[0, 1, -1], 0:10].T.plot(style="o")
    ax.set_xlabel("Number of stations")
    ax.set_ylabel("Throughput [Mb/s]")
    ax.set_ylim(0, 32)
    x_ticks = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ax.set_xticks(range(len(x_ticks)))
    ax.set_xticklabels(x_ticks)
    ax.legend(results.iloc[[0, 1, -1], 10].tolist())
    ax.text(
        0.60,
        0.11,
        "MSE for DCF-SimPy vs:\nns-3: {}\nAnalitical model: {}".format(
            *results.iloc[-1, 11:13].tolist()
        ),
        bbox={"facecolor": "none", "pad": 10, "edgecolor": "grey"},
        ha="left",
        va="center",
        transform=ax.transAxes,
    )


def plot_thr(times_thr):
    times_thr = float("{:.4f}".format(times_thr))
    matlab_thr = 34.6014
    ns_3_thr = 36.1225
    names = ["Matlab", "NS-3", "Times-DCF"]
    values = [matlab_thr, ns_3_thr, times_thr]
    plt.figure()
    plt.bar(names, values)
    for index, value in enumerate(values):
        plt.text(index, value + 0.5, str(value))
    plt.ylabel("Throughput [Mb/s]")
    plt.title("Throughput comparison")
    plt.show()


# def calculate_mean():
#     with open("results.txt", "r") as f:
#         res = {'1': [0,0], '2': [0,0],'3': [0,0],'4': [0,0],'5': [0,0],'6': [0,0],'7': [0,0],'8': [0,0],'9': [0,0],'10': [0,0]}
#         line = f.readline()
#         while line:
#             n = line.split(": ")[1].replace("\n", "")
#             res[n][0] += float(f.readline().split(": ")[1].split(" ")[0].replace("\n", ""))
#             res[n][1] += float(f.readline().split(": ")[1].replace("\n", ""))
#             line = f.readline()
#         for key in res.keys():
#             res[key][0] = "{:.4f}".format(res[key][0] / 10)
#             res[key][1] = "{:.4f}".format(res[key][1] / 10)
#         frame = pd.DataFrame.from_dict(res)
#         frame.to_csv("results.csv")
#         print(frame)


if __name__ == "__main__":
    file = "15-1023-10-1594202254.353538-mean.csv"
    calculate_p_coll_mse(file)
    calculate_thr_mse(file)
    plot_thr(t.get_thr())
    # calculate_mean()
