import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import pandas as pd
import simpy

from .Times import *

colors = [
    "\033[30m",
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[34m",
    "\033[35m",
    "\033[36m",
    "\033[37m",
]  # colors to distinguish stations in output


@dataclass()
class Config:
    data_size: int = 1472  # size od payload in b
    cw_min: int = 15  # min cw window size
    cw_max: int = 1023  # max cw window size
    r_limit: int = 7
    mcs: int = 7


big_num = 10000000  # some big number for transmitting query preemption


def log(station, mes: str) -> None:
    logging.info(
        f"{station.col}Time: {station.env.now} Station: {station.name} Message: {mes}"
    )


class Station:
    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        channel: dataclass,
        config: Config = Config(),
    ):
        self.config = config
        self.times = Times(config.data_size, config.mcs)
        self.name = name  # name of the station
        self.env = env  # current environment
        self.col = random.choice(colors)  # color of output
        self.frame_to_send = None  # the frame object which is next to send
        self.succeeded_transmissions = 0  # all succeeded transmissions for station
        self.failed_transmissions = 0  # all failed transmissions for station
        self.failed_transmissions_in_row = (
            0  # all failed transmissions for station without succeeded transmissions
        )
        self.cw_min = config.cw_min  # cw min parameter value
        self.cw_max = config.cw_max  # cw max parameter value
        self.channel = channel  # channel object
        env.process(self.start())  # simulation process
        self.process = None  # waiting back off process

    def start(self):
        while True:
            self.frame_to_send = self.generate_new_frame()
            was_sent = False
            while not was_sent:
                self.process = self.env.process(self.wait_back_off())
                yield self.process
                was_sent = yield self.env.process(self.send_frame())

    def wait_back_off(self):
        back_off_time = self.generate_new_back_off_time(
            self.failed_transmissions_in_row
        )  # generate the new Back Off time
        while back_off_time > -1:
            try:
                with self.channel.tx_lock.request() as req:  # wait for the lock/idle channel
                    yield req
                back_off_time += Times.t_difs  # add DIFS time
                log(self, f"Starting to wait backoff: ({back_off_time})u...")
                start = self.env.now  # store the current simulation time
                self.channel.back_off_list.append(
                    self
                )  # join the list off stations which are waiting Back Offs
                yield self.env.timeout(
                    back_off_time
                )  # join the environment action queue
                log(self, f"Backoff waited, sending frame...")
                back_off_time = -1  # leave the loop
                self.channel.back_off_list.remove(
                    self
                )  # leave the waiting list as Back Off was waited successfully
            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                log(self, "Waiting was interrupted, waiting to resume backoff...")
                back_off_time -= (
                    self.env.now - start
                )  # set the Back Off to the remaining one
                back_off_time -= 9  # simulate the delay of sensing the channel state

    def send_frame(self):
        self.channel.tx_list.append(self)  # add station to currently transmitting list
        res = self.channel.tx_queue.request(  # create request basing on this station frame length
            priority=(big_num - self.frame_to_send.frame_time)
        )
        try:
            result = yield res | self.env.timeout(
                0
            )  # try to hold transmitting lock(station with the longest frame will get this)
            if (
                res not in result
            ):  # check if this station got lock, if not just wait you frame time
                raise simpy.Interrupt("There is a longer frame...")
            with self.channel.tx_lock.request() as lock:  # this station has the longest frame so hold the lock
                yield lock
                log(self, self.channel.back_off_list)
                for (
                    station
                ) in (
                    self.channel.back_off_list
                ):  # stop all station which are waiting backoff as channel is not idle
                    station.process.interrupt()
                log(self, self.frame_to_send.frame_time)
                yield self.env.timeout(
                    self.frame_to_send.frame_time
                )  # wait this station frame time
                self.channel.back_off_list.clear()  # channel idle, clear backoff waiting list
                was_sent = self.check_collision()  # check if collision occurred
                if was_sent:  # transmission successful
                    yield self.env.timeout(
                        self.times.get_ack_frame_time()
                    )  # wait ack
                    self.channel.tx_list.clear()  # clear transmitting list
                    self.channel.tx_queue.release(res)  # leave the transmitting queue
                    return True
            # there was collision
            self.channel.tx_list.clear()  # clear transmitting list
            self.channel.tx_queue.release(res)  # leave the transmitting queue
            self.channel.tx_queue = simpy.PreemptiveResource(
                self.env, capacity=1
            )  # create new empty transmitting queue
            yield self.env.timeout(
                self.times.ack_timeout
            )  # simulate ack timeout after failed transmission
            return False
        except simpy.Interrupt:  # this station does not have the longest frame, waiting frame time
            yield self.env.timeout(self.frame_to_send.frame_time)
        was_sent = self.check_collision()
        if was_sent:  # check if collision occurred
            yield self.env.timeout(
                self.times.get_ack_frame_time()
            )  # wait ack
        else:
            log(self, "waiting wck timeout slave")
            yield self.env.timeout(
                Times.ack_timeout
            )  # simulate ack timeout after failed transmission
        return was_sent

    def check_collision(self):  # check if the collision occurred
        if (
            len(self.channel.tx_list) > 1
        ):  # check if there was more then one station transmitting
            self.sent_failed()
            return False
        else:
            self.sent_completed()
            return True

    def generate_new_back_off_time(self, failed_transmissions_in_row):
        upper_limit = (
            pow(2, failed_transmissions_in_row) * (self.cw_min + 1) - 1
        )  # define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = (
            upper_limit if upper_limit <= self.cw_max else self.cw_max
        )  # set upper limit to CW Max if is bigger then this parameter
        back_off = random.randint(0, upper_limit)  # draw the back off value
        self.channel.backoffs[back_off][
            self.channel.n_of_stations
        ] += 1  # store drawn value for future analyzes
        return back_off * self.times.t_slot

    def generate_new_frame(self):
        frame_length = self.times.get_ppdu_frame_time()
        return Frame(
            frame_length, self.name, self.col, self.config.data_size, self.env.now
        )

    def sent_failed(self):
        log(self, "There was a collision")
        self.frame_to_send.number_of_retransmissions += 1
        self.channel.failed_transmissions += 1
        self.failed_transmissions += 1
        self.failed_transmissions_in_row += 1
        log(self, self.channel.failed_transmissions)
        if self.frame_to_send.number_of_retransmissions > self.config.r_limit:
            self.frame_to_send = self.generate_new_frame()
            self.failed_transmissions_in_row = 0

    def sent_completed(self):
        log(
            self,
            f"Successfully sent frame, waiting ack: {self.times.get_ack_frame_time()}",
        )
        self.frame_to_send.t_end = self.env.now
        self.frame_to_send.t_to_send = (
            self.frame_to_send.t_end - self.frame_to_send.t_start
        )
        self.channel.succeeded_transmissions += 1
        self.succeeded_transmissions += 1
        self.failed_transmissions_in_row = 0
        self.channel.bytes_sent += self.frame_to_send.data_size
        return True


@dataclass()
class Channel:
    tx_queue: simpy.PreemptiveResource  # lock for the stations with the longest frame to transmit
    tx_lock: simpy.Resource  # channel lock (locked when there is ongoing transmission)
    n_of_stations: int  # number of transmitting stations in the channel
    backoffs: Dict[int, Dict[int, int]]
    tx_list: List[Station] = field(
        default_factory=list
    )  # transmitting stations in the channel
    back_off_list: List[Station] = field(
        default_factory=list
    )  # stations in backoff phase
    failed_transmissions: int = 0  # total failed transmissions
    succeeded_transmissions: int = 0  # total succeeded transmissions
    bytes_sent: int = 0  # total bytes sent


@dataclass()
class Frame:
    frame_time: int  # time of the frame
    station_name: str  # name of the owning it station
    col: str  # output color
    data_size: int  # payload size
    t_start: int  # generation time
    number_of_retransmissions: int = 0  # retransmissions count
    t_end: int = None  # sent time
    t_to_send: int = None  # how much time it took to sent successfully

    def __repr__(self):
        return (
            self.col
            + "Frame: start=%d, end=%d, frame_time=%d, retransmissions=%d"
            % (self.t_start, self.t_end, self.t_to_send, self.number_of_retransmissions)
        )


def run_simulation(
    number_of_stations: int,
    seed: int,
    simulation_time: int,
    skip_results: bool,
    config: Config,
    backoffs: Dict[int, Dict[int, int]],
    results: Dict[str, List[str]],
):
    random.seed(seed)
    environment = simpy.Environment()
    channel = Channel(
        simpy.PreemptiveResource(environment, capacity=1),
        simpy.Resource(environment, capacity=1),
        number_of_stations,
        backoffs,
    )
    for i in range(1, number_of_stations + 1):
        Station(environment, "Station {}".format(i), channel, config)
    environment.run(until=simulation_time * 1000000)
    p_coll = "{:.4f}".format(
        channel.failed_transmissions
        / (channel.failed_transmissions + channel.succeeded_transmissions)
    )
    print(
        f"SEED = {seed} N={number_of_stations} CW_MIN = {config.cw_min} CW_MAX = {config.cw_max}  PCOLL: {p_coll} THR:"
        f" {(channel.bytes_sent*8)/(simulation_time * 1000000)} "
        f"FAILED_TRANSMISSIONS: {channel.failed_transmissions}"
        f" SUCCEEDED_TRANSMISSION {channel.succeeded_transmissions}"
    )
    if not skip_results:
        add_to_results(
            p_coll, channel, number_of_stations, results, seed, simulation_time, config
        )


def add_to_results(p_coll, channel, n, results, seed, simulation_time, config: Config):
    results.setdefault("TIMESTAMP", []).append(datetime.fromtimestamp(time.time()))
    results.setdefault("CW_MIN", []).append(config.cw_min)
    results.setdefault("CW_MAX", []).append(config.cw_max)
    results.setdefault("N_OF_STATIONS", []).append(n)
    results.setdefault("SEED", []).append(seed)
    results.setdefault("P_COLL", []).append(p_coll)
    results.setdefault("THR", []).append(
        (channel.bytes_sent * 8) / (simulation_time * 1000000)
    )
    results.setdefault("FAILED_TRANSMISSIONS", []).append(channel.failed_transmissions)
    results.setdefault("SUCCEEDED_TRANSMISSIONS", []).append(
        channel.succeeded_transmissions
    )
    results.setdefault("PAYLOAD", []).append(config.data_size)
    results.setdefault("MCS", []).append(config.mcs)


def save_results(
    results: Dict[str, str], backoffs: Dict[int, Dict[int, int]], function_name
):
    path = f"{os.getcwd()}/results/{datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%s')}-{function_name}/"
    os.mkdir(path)
    pd.DataFrame(results).to_csv(f"{path}results.csv", index=False)
    pd.DataFrame(dict(sorted(backoffs.items()))).to_csv(
        f"{path}backoffs.csv", index=False,
    )
    return path
