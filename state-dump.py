import argparse
import asyncio
import logging
import datetime
import toml
from nimiqclient import *

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL = "INFO"


class Range(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __eq__(self, other):
        return self.start <= other <= self.end


async def run_client(host, port, vrf, parent_hash, parent_election_hash,
                     history_root, block_number, file_path):
    async with NimiqClient(
        scheme="ws", host=host, port=port
    ) as client:
        file = open(file_path, "w")

        # Get the chain data
        block = await client.get_latest_block()
        timestamp = datetime.datetime.now(datetime.timezone.utc)

        logging.info(
            f"Running for block number: {block.number}, block hash: "
            f"{block.hash}")

        # Get accounts and validators
        accounts = await client.get_accounts()
        validators = await client.get_validators()

        toml_output = dict()

        # Parse the accounts objects to arrays of dictionaries with the
        # expected TOML data
        parsed_basic_accounts = []
        parsed_htlcs = []
        parsed_vesting = []
        for account in accounts.data:
            if account.type == 'htlc':
                parsed_htlcs.append({'address': account.address,
                                     'sender': account.sender,
                                     'recepient': account.receipient,
                                     'balance': account.balance,
                                     'hash_root': account.hashRoot,
                                     'hash_count': account.hashCount,
                                     'timeout': account.timeout,
                                     'total_acount': account.totalAmount})

            elif account.type == 'vesting':
                parsed_vesting.append({'address': account.address,
                                       'owner': account.owner,
                                       'balance': account.balance,
                                       'start_time': account.startTime,
                                       'time_step': account.timeStep,
                                       'step_amount': account.stepAmount,
                                       'total_amount': account.totalAmount})
            elif account.type == 'basic':
                parsed_basic_accounts.append({
                    'address': account.address,
                    'balance': account.balance,
                })
            else:
                logging.debug(f"Ignoring account of type {account.type}")

        # Parse the validator objects to arrays of dictionaries with the
        # expected TOML data
        parsed_validators = []
        parsed_stakers = []
        for validator in validators.data:
            stakers = await client.get_stakers_by_validator_address(
                validator.address)
            parsed_validators.append(
                {'validator_address': validator.address,
                 'signing_key': validator.signingKey,
                 'voting_key': validator.votingKey,
                 'reward_address': validator.rewardAddress,
                 'inactive_from': validator.inactivityFlag,
                 'retired': validator.retired,
                 'jailed_from': validator.jailedFrom,
                 })
            logging.info(
                f"Found validator, address: {validator.address}, balance: "
                f"{validator.balance}")
            for staker in stakers.data:
                # Enforce minimum stake
                if staker.balance < 10000000:
                    staker.balance = 10000000
                parsed_stakers.append(
                    {'staker_address': staker.address,
                     'balance': staker.balance,
                     'delegation': staker.delegation,
                     'inactive_balance': staker.inactiveBalance,
                     'inactive_from': staker.inactiveFrom})

        # Now build a dictionary for taking it to TOML
        toml_output['name'] = 'test-albatross'
        toml_output['network'] = 'TestAlbatross'
        toml_output['timestamp'] = timestamp.isoformat()
        toml_output['vrf_seed'] = vrf
        toml_output['parent_hash'] = parent_hash
        toml_output['history_root'] = history_root
        toml_output['parent_election_hash'] = parent_election_hash
        toml_output['block_number'] = block_number
        if len(parsed_basic_accounts) != 0:
            toml_output['basic_accounts'] = parsed_basic_accounts
        if len(parsed_vesting) != 0:
            toml_output['vesting_accounts'] = parsed_vesting
        if len(parsed_htlcs) != 0:
            toml_output['htlc_accounts'] = parsed_htlcs
        if len(parsed_validators) != 0:
            toml_output['validators'] = parsed_validators
        if len(parsed_stakers) != 0:
            toml_output['stakers'] = parsed_stakers

        file.write("\n")
        file.write(
            f"# File generated at {timestamp.isoformat()} ")
        file.write("from Nimiq Pos chain\n")
        file.write(f"# - Block height: {block.number}\n")
        file.write(f"# - Block hash: {block.hash}\n\n")

        toml.dump(toml_output, file)
        logging.info(f"Output written at '{file_path}'")
        file.close()


def parse_args():
    """
    Parse command line arguments:
    - RPC host
    - RPC port
    - Output file
    - Genesis VRF seed
    - Genesis parent hash
    - Genesis parent election hash
    - Genesis block number

    :return The parsed command line arguments.
    :rtype: Namespace
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-H', '--host', type=str, required=True,
                        help="RPC host for the Nimiq client RPC connection")
    parser.add_argument('-P', '--port', type=int, required=True,
                        help="RPC port for the Nimiq client RPC connection")
    parser.add_argument('-f', '--file', type=str, required=True,
                        help="File where the data is going to be dumped")
    parser.add_argument('-V', '--vrf', type=str, required=True,
                        help="VRF seed for the generated PoS genesis TOML")
    parser.add_argument('-p', '--parent', type=str, required=True,
                        help="Parent hash for the generated PoS genesis TOML")
    parser.add_argument('-e', '--election', type=str, required=True,
                        help=("Parent election hash for the generated PoS "
                              "genesis TOML"))
    parser.add_argument('-hr', '--history', type=str, required=True,
                        help=("History root for the generated PoS genesis TOML"
                              ))
    parser.add_argument('-b', '--block', type=int, required=True,
                        help="Genesis initial block number")
    parser.add_argument("--verbose", "-v", dest="log_level",
                        action="append_const", const=-1)
    return parser.parse_args()


def setup_logging(args):
    """
    Sets-up logging according to the arguments received.

    :params args: Command line arguments of the program
    :type args: Namespace
    """
    # Adjust log level accordingly
    log_level = LOG_LEVELS.index(DEFAULT_LOG_LEVEL)
    for adjustment in args.log_level or ():
        log_level = min(len(LOG_LEVELS) - 1, max(log_level + adjustment, 0))

    log_level_name = LOG_LEVELS[log_level]
    logging.getLogger().setLevel(log_level_name)
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')


def main():
    # Parse arguments
    args = parse_args()

    # Setup logging
    setup_logging(args)

    asyncio.get_event_loop().run_until_complete(
        run_client(args.host, args.port, args.vrf, args.parent, args.election,
                   args.history, args.block, args.file)
    )


if __name__ == "__main__":
    main()
